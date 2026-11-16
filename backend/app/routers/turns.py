import asyncio
import json
import logging
from collections.abc import AsyncIterator
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app import deps
from app.audio.stt import SpeechToText
from app.audio.tts import SpeechSynth
from app.audio.wav import read_wav, to_model_input
from app.db import SessionFactory
from app.llm.base import TutorLLM
from app.models import Learner, Session, Turn
from app.schemas import TurnAccepted
from app.tutor.pipeline import SseEvent, stream_reply

router = APIRouter(prefix="/api/turns", tags=["turns"])
logger = logging.getLogger(__name__)

MAX_AUDIO_MS = 120_000
MAX_TEXT_CHARS = 800

_running: dict[int, asyncio.Event] = {}


class TurnTextIn(BaseModel):
    session_id: int
    text: str = Field(min_length=1, max_length=MAX_TEXT_CHARS)


async def _next_seq(db: AsyncSession, session_id: int) -> int:
    current = (
        await db.execute(select(func.max(Turn.seq)).where(Turn.session_id == session_id))
    ).scalar()
    return int(current or 0) + 1


async def _active_session(db: AsyncSession, session_id: int) -> Session:
    session = (
        await db.execute(select(Session).where(Session.id == session_id))
    ).scalar_one_or_none()
    if session is None:
        raise HTTPException(status_code=404, detail=f"session {session_id} not found")
    if session.ended_at is not None:
        raise HTTPException(status_code=409, detail="session already ended")
    return session


async def _store_turn(
    db: AsyncSession, session: Session, transcript: str, no_speech: bool, audio_ms: int
) -> Turn:
    turn = Turn(
        session_id=session.id,
        seq=await _next_seq(db, session.id),
        transcript=transcript,
        no_speech=no_speech,
    )
    db.add(turn)
    await db.flush()
    logger.info(
        "turn %s stored in session %s (no_speech=%s, chars=%d)",
        turn.id,
        session.id,
        no_speech,
        len(transcript),
    )
    return turn


@router.post("/text", response_model=TurnAccepted, status_code=201)
async def create_text_turn(
    payload: TurnTextIn, db: AsyncSession = Depends(deps.get_db)
) -> TurnAccepted:
    session = await _active_session(db, payload.session_id)
    text = " ".join(payload.text.split())
    if not text:
        raise HTTPException(status_code=400, detail="empty message")

    turn = await _store_turn(db, session, text, no_speech=False, audio_ms=0)
    return TurnAccepted(
        turn_id=turn.id,
        transcript=turn.transcript,
        no_speech=turn.no_speech,
        audio_ms=0,
    )


@router.post("", response_model=TurnAccepted, status_code=201)
async def create_turn(
    session_id: int = Form(...),
    file: UploadFile = File(...),
    db: AsyncSession = Depends(deps.get_db),
    stt: SpeechToText = Depends(deps.get_stt_dep),
) -> TurnAccepted:
    session = await _active_session(db, session_id)

    raw = await file.read()
    if not raw:
        raise HTTPException(status_code=400, detail="empty audio upload")

    try:
        wav = read_wav(raw)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    if wav.duration_ms > MAX_AUDIO_MS:
        raise HTTPException(
            status_code=413, detail=f"recording too long ({wav.duration_ms} ms)"
        )

    try:
        samples = to_model_input(wav)
        result = await asyncio.to_thread(stt.transcribe, samples)
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    turn = await _store_turn(
        db, session, result.text, no_speech=result.no_speech, audio_ms=wav.duration_ms
    )
    return TurnAccepted(
        turn_id=turn.id,
        transcript=turn.transcript,
        no_speech=turn.no_speech,
        audio_ms=wav.duration_ms,
    )


def _sse(event: SseEvent) -> str:
    return f"event: {event.event}\ndata: {json.dumps(event.data, ensure_ascii=False)}\n\n"


async def _reply_stream(turn_id: int, llm: TutorLLM, tts: SpeechSynth) -> AsyncIterator[str]:
    cancel = asyncio.Event()
    _running[turn_id] = cancel
    try:
        async with SessionFactory() as db:
            turn = (
                await db.execute(select(Turn).where(Turn.id == turn_id))
            ).scalar_one_or_none()
            if turn is None:
                yield _sse(SseEvent("error", {"code": "not_found", "message": "unknown turn"}))
                return

            session = (
                await db.execute(select(Session).where(Session.id == turn.session_id))
            ).scalar_one_or_none()
            if session is None:
                yield _sse(SseEvent("error", {"code": "not_found", "message": "unknown session"}))
                return

            learner = (
                await db.execute(select(Learner).where(Learner.id == session.learner_id))
            ).scalar_one_or_none()
            if learner is None:
                yield _sse(SseEvent("error", {"code": "not_found", "message": "unknown learner"}))
                return

            async for event in stream_reply(db, session, learner, turn, llm, tts):
                if cancel.is_set():
                    logger.info("reply for turn %s cancelled", turn_id)
                    break
                yield _sse(event)
    except Exception as exc:  # noqa: BLE001
        logger.exception("reply stream failed for turn %s", turn_id)
        yield _sse(SseEvent("error", {"code": "reply_failed", "message": str(exc)}))
    finally:
        _running.pop(turn_id, None)


@router.get("/{turn_id}/reply")
async def turn_reply(
    turn_id: int,
    llm: TutorLLM = Depends(deps.get_llm_dep),
    tts: SpeechSynth = Depends(deps.get_tts_dep),
) -> StreamingResponse:
    return StreamingResponse(
        _reply_stream(turn_id, llm, tts),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-transform",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.post("/{turn_id}/abandon")
async def abandon_turn(
    turn_id: int, db: AsyncSession = Depends(deps.get_db)
) -> dict:
    event = _running.get(turn_id)
    if event is not None:
        event.set()

    turn = (
        await db.execute(select(Turn).where(Turn.id == turn_id))
    ).scalar_one_or_none()
    if turn is None:
        raise HTTPException(status_code=404, detail=f"turn {turn_id} not found")

    if turn.abandoned_at is None:
        turn.abandoned_at = datetime.now(UTC)
    return {"turn_id": turn_id, "abandoned": True, "was_running": event is not None}