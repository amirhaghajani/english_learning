import logging

from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app import deps
from app.audio.stt import SpeechToText
from app.audio.tts import SpeechSynth
from app.config import settings
from app.llm.base import TutorLLM
from app.rag.index import CurriculumRetriever
from app.schemas import HealthOut

router = APIRouter()
logger = logging.getLogger(__name__)


async def _probe(fn, label: str) -> tuple[bool, str]:
    try:
        return fn()
    except Exception as exc:  # noqa: BLE001
        return False, f"{label} probe failed: {exc}"


@router.get("/api/healthz", response_model=HealthOut)
async def healthz(
    db: AsyncSession = Depends(deps.get_db),
    llm: TutorLLM = Depends(deps.get_llm_dep),
    stt: SpeechToText = Depends(deps.get_stt_dep),
    tts: SpeechSynth = Depends(deps.get_tts_dep),
) -> HealthOut:
    database_ok = True
    try:
        await db.execute(text("SELECT 1"))
    except Exception as exc:  # noqa: BLE001
        database_ok = False
        logger.warning("healthz: database unreachable: %s", exc)

    llm_ok, llm_detail = await _probe(llm.probe, "llm")
    stt_ok, stt_detail = await _probe(stt.probe, "stt")
    tts_ok, tts_detail = await _probe(tts.probe, "tts")

    rag_backend, rag_detail = "none", ""
    try:
        rag_backend, rag_detail = CurriculumRetriever(db).status()
    except Exception as exc:  # noqa: BLE001
        rag_detail = f"rag probe failed: {exc}"

    return HealthOut(
        status="ok" if (database_ok and llm_ok) else "degraded",
        database=database_ok,
        database_backend="sqlite" if settings.is_sqlite else "postgresql",
        llm_provider=settings.llm_provider,
        llm_model=llm.model,
        llm_reachable=llm_ok,
        stt_backend=stt.name,
        stt_ready=stt_ok,
        tts_backend=tts.name,
        tts_ready=tts_ok,
        rag_backend=rag_backend,
        details={"llm": llm_detail, "stt": stt_detail, "tts": tts_detail, "rag": rag_detail},
    )