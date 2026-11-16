import logging

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app import deps
from app.rag.index import CurriculumRetriever
from app.schemas import IngestResult

router = APIRouter(prefix="/api/admin", tags=["admin"])
logger = logging.getLogger(__name__)


@router.post("/ingest", response_model=IngestResult)
async def ingest(db: AsyncSession = Depends(deps.get_db)) -> IngestResult:
    retriever = CurriculumRetriever(db)
    outcome = await retriever.ingest()
    logger.info("ingest finished: %s", outcome)
    return IngestResult(
        documents=outcome.documents,
        upserted=outcome.upserted,
        skipped=outcome.skipped,
        embedded=outcome.embedded,
        backend=outcome.backend,
        warnings=outcome.warnings,
    )