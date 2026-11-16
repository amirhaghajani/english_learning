import asyncio
import base64
import json
import logging
import time
from collections.abc import AsyncIterator, Iterator
from dataclasses import dataclass, field
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.audio.tts import SpeechSynth
from app.config import settings
from app.llm.base import LLMError, ReplyRequest, TutorLLM
from app.llm.prompt import PromptContext, RecurringError, build_messages, build_system_prompt
from app.models import Correction, Learner, Scenario, Session, Turn
from app.rag.index import CurriculumRetriever
from app.tutor.feedback import SENTINEL_RE, ParsedCorrection, split_reply
from app.tutor.sentences import split_sentences

logger = logging.getLogger(__name__)

_SENTINEL = object()

SENTENCE_GAP_MS = 220


@dataclass
class SseEvent:
    event: str
    data: dict


def format_sse(event: SseEvent) -> str:
    return f"event: {event.event}\ndata: {json.dumps(event.data, ensure_ascii=False)}\n\n"


def speak_text_events(text: str, tts: SpeechSynth) -> list[SseEvent]:
    """Synthesize one line of speech into the same event shapes the reply stream uses."""
    return _Speaker(tts).say(text)


@dataclass
class ReplyOutcome:
    prose: str = ""
    corrections: list[ParsedCorrection] = field(default_factory=list)
    audio_ms: int = 0


async def _aiter_sync(iterator: Iterator[str]) -> AsyncIterator[str]:
    loop = asyncio.get_running_loop()
    queue: asyncio.Queue = asyncio.Queue()

    def worker() -> None:
        try:
            for item in iterator:
                loop.call_soon_threadsafe(queue.put_nowait, item)
        except BaseException as exc:  # noqa: BLE001
            loop.call_soon_threadsafe(queue.put_nowait, exc)
        finally:
            loop.call_soon_threadsafe(queue.put_nowait, _SENTINEL)

    loop.run_in_executor(None, worker)
    while True:
        item = await queue.get()
        if item is _SENTINEL:
            return
        if isinstance(item, BaseException):
            raise item
        yield item


def _is_closed(text: str) -> bool:
    stripped = text.rstrip()
    return bool(stripped) and stripped[-1] in ".!?\"')]"


def _pcm_ms(num_bytes: int, sample_rate: int) -> int:
    if sample_rate <= 0:
        return 0
    return int(round(num_bytes / 2 / sample_rate * 1000))


class _Speaker:
    def __init__(self, tts: SpeechSynth) -> None:
        self.tts = tts
        self.index = 0
        self.audio_ms = 0

    def say(self, text: str) -> list[SseEvent]:
        sentence_index = self.index
        self.index += 1
        events: list[SseEvent] = [SseEvent("sentence", {"index": sentence_index, "text": text})]
        seq = 0
        for pcm in self.tts.synthesize(text):
            rate = self.tts.sample_rate
            events.append(
                SseEvent(
                    "audio",
                    {
                        "index": sentence_index,
                        "seq": seq,
                        "pcm_b64": base64.b64encode(pcm).decode("ascii"),
                        "sample_rate": rate,
                        "sentence": text,
                    },
                )
            )
            self.audio_ms += _pcm_ms(len(pcm), rate)
            seq += 1

        gap = self._trailing_pause()
        if gap:
            rate = self.tts.sample_rate
            events.append(
                SseEvent(
                    "audio",
                    {
                        "index": sentence_index,
                        "seq": seq,
                        "pcm_b64": base64.b64encode(gap).decode("ascii"),
                        "sample_rate": rate,
                        "sentence": text,
                    },
                )
            )
            self.audio_ms += _pcm_ms(len(gap), rate)
        return events

    def _trailing_pause(self) -> bytes:
        rate = getattr(self.tts, "sample_rate", 0) or 0
        if rate <= 0:
            return b""
        return b"\x00\x00" * int(rate * SENTENCE_GAP_MS / 1000)


async def _load_context(
    db: AsyncSession, session: Session
) -> tuple[Scenario | None, list[Turn]]:
    scenario = None
    if session.scenario_slug:
        scenario = (
            await db.execute(select(Scenario).where(Scenario.slug == session.scenario_slug))
        ).scalar_one_or_none()

    stmt = select(Turn).where(Turn.session_id == session.id).order_by(Turn.seq)
    return scenario, list((await db.execute(stmt)).scalars().all())


async def _persist(
    db: AsyncSession,
    turn: Turn,
    prose: str,
    corrections: list[ParsedCorrection],
    audio_ms: int,
    abandoned: bool = False,
) -> None:
    turn.reply_text = prose
    turn.audio_ms = audio_ms
    if abandoned and turn.abandoned_at is None:
        turn.abandoned_at = datetime.now(UTC)

    for item in corrections:
        db.add(
            Correction(
                turn_id=turn.id,
                said=item.said,
                replacement=item.replacement,
                category=item.category,
                why=item.why,
                severity=item.severity,
            )
        )
    await db.commit()


async def stream_reply(
    db: AsyncSession,
    session: Session,
    learner: Learner,
    turn: Turn,
    llm: TutorLLM,
    tts: SpeechSynth,
) -> AsyncIterator[SseEvent]:
    speaker = _Speaker(tts)
    started = time.monotonic()

    yield SseEvent("meta", {"turn_id": turn.id, "reply_id": f"turn-{turn.id}"})

    scenario, all_turns = await _load_context(db, session)
    history = [t for t in all_turns if t.seq < turn.seq][-settings.history_turns :]

    if turn.no_speech:
        line = "Sorry, I didn't catch that. Could you say it once more?"
        for event in speaker.say(line):
            yield event
        await _persist(db, turn, line, [], speaker.audio_ms)
        yield SseEvent("corrections", {"items": []})
        yield SseEvent("done", {"index": speaker.index - 1, "audio_ms": speaker.audio_ms})
        return

    retriever = CurriculumRetriever(db)
    curriculum = []
    recurring: list[RecurringError] = []
    try:
        curriculum = await retriever.search(
            turn.transcript, top_k=settings.rag_top_k, max_level=learner.cefr.value
        )
        rows = await retriever.recurring_errors(learner.id)
        recurring = [RecurringError(**row) for row in rows]
    except Exception as exc:  # noqa: BLE001
        logger.warning("retrieval failed for turn %s: %s", turn.id, exc)

    ctx = PromptContext(
        learner=learner,
        scenario=scenario,
        curriculum=curriculum,
        recurring=recurring,
        history=history,
        latest_message=turn.transcript,
    )
    request = ReplyRequest(
        system=build_system_prompt(ctx),
        messages=build_messages(ctx, turn.transcript),
        temperature=0.7,
    )

    buffer = ""
    emitted = 0

    def speakable(text: str) -> str:
        match = SENTINEL_RE.search(text)
        return text[: match.start()] if match else text

    try:
        async for delta in _aiter_sync(llm.stream(request)):
            buffer += delta
            visible = speakable(buffer)
            parts = split_sentences(visible)
            emittable = parts if _is_closed(visible) else parts[:-1]
            while emitted < len(emittable):
                sentence = emittable[emitted]
                emitted += 1
                for event in speaker.say(sentence):
                    yield event
    except LLMError as exc:
        logger.warning("LLM error on turn %s: %s", turn.id, exc.message)
        await _persist(db, turn, buffer.strip(), [], speaker.audio_ms)
        yield SseEvent("error", {"code": exc.code, "message": exc.message})
        return
    except Exception as exc:  # noqa: BLE001
        logger.exception("unexpected failure streaming turn %s", turn.id)
        await _persist(db, turn, buffer.strip(), [], speaker.audio_ms)
        yield SseEvent("error", {"code": "reply_failed", "message": str(exc)})
        return

    for sentence in split_sentences(speakable(buffer))[emitted:]:
        for event in speaker.say(sentence):
            yield event

    prose, corrections = split_reply(
        buffer, limit=settings.max_corrections, ground_against=turn.transcript
    )
    await _persist(db, turn, prose, corrections, speaker.audio_ms)

    yield SseEvent(
        "corrections",
        {
            "items": [
                {
                    "said": c.said,
                    "replacement": c.replacement,
                    "category": c.category,
                    "why": c.why,
                    "severity": c.severity,
                }
                for c in corrections
            ]
        },
    )
    yield SseEvent("done", {"index": max(speaker.index - 1, 0), "audio_ms": speaker.audio_ms})
    logger.info(
        "turn %s done in %.2fs (%d corrections)",
        turn.id,
        time.monotonic() - started,
        len(corrections),
    )