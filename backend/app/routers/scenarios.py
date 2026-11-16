from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app import deps
from app.models import Scenario
from app.schemas import ScenarioOut

router = APIRouter(prefix="/api/scenarios", tags=["scenarios"])


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