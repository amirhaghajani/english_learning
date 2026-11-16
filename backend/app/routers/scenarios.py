import asyncio
import logging
from collections.abc import AsyncIterator

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app import deps
from app.audio.tts import SpeechSynth
from app.models import Scenario, Session
from app.schemas import ScenarioOut
from app.tutor.pipeline import SseEvent, format_sse, speak_text_events

router = APIRouter(prefix="/api/scenarios", tags=["scenarios"])
logger = logging.getLogger(__name__)

_SSE_HEADERS = {
    "Cache-Control": "no-cache, no-transform",
    "Connection": "keep-alive",
    "X-Accel-Buffering": "no",
}


@router.get("", response_model=list[ScenarioOut])
async def list_scenarios(
    level: str | None = Query(default=None),
    db: AsyncSession = Depends(deps.get_db),
) -> list[ScenarioOut]:
    stmt = select(Scenario).order_by(Scenario.level, Scenario.title)
    if level:
        stmt = stmt.where(Scenario.level == level.upper())
    rows = (await db.execute(stmt)).scalars().all()
    return [ScenarioOut.model_validate(row) for row in rows]


async def _opening_stream(text: str, tts: SpeechSynth) -> AsyncIterator[str]:
    events, audio_ms = await asyncio.to_thread(speak_text_events, text, tts)
    for event in events:
        yield format_sse(event)
    yield format_sse(SseEvent("done", {"index": 0, "audio_ms": audio_ms}))


@router.get("/{slug}/opening")
async def scenario_opening(
    slug: str,
    session_id: int | None = Query(default=None),
    db: AsyncSession = Depends(deps.get_db),
    tts: SpeechSynth = Depends(deps.get_tts_dep),
) -> StreamingResponse:
    scenario = (
        await db.execute(select(Scenario).where(Scenario.slug == slug))
    ).scalar_one_or_none()
    if scenario is None:
        raise HTTPException(status_code=404, detail=f"scenario '{slug}' not found")

    line = (scenario.opening_line or "").strip()
    if not line:
        raise HTTPException(
            status_code=404, detail=f"scenario '{slug}' has no opening line"
        )

    if session_id is not None:
        session = (
            await db.execute(select(Session).where(Session.id == session_id))
        ).scalar_one_or_none()
        if session is not None:
            session.opening_line = line
            await db.commit()

    return StreamingResponse(
        _opening_stream(line, tts),
        media_type="text/event-stream",
        headers=_SSE_HEADERS,
    )