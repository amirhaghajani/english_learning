from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app import deps
from app.config import settings
from app.models import Learner, Scenario, Session, SessionMode, Turn
from app.schemas import SessionCreate, SessionOut

router = APIRouter(prefix="/api/sessions", tags=["sessions"])

_EAGER = {
    "turns": selectinload(Session.turns).selectinload(Turn.corrections),
}


async def _get_session(db: AsyncSession, session_id: int, learner_id: int | None = None) -> Session:
    stmt = select(Session).options(*_EAGER.values()).where(Session.id == session_id)
    session = (await db.execute(stmt)).scalar_one_or_none()
    if session is None or (learner_id is not None and session.learner_id != learner_id):
        raise HTTPException(status_code=404, detail=f"session {session_id} not found")
    return session


@router.get("", response_model=list[SessionOut])
async def list_sessions(
    learner_id: int = Query(...),
    db: AsyncSession = Depends(deps.get_db),
) -> list[SessionOut]:
    stmt = (
        select(Session)
        .options(*_EAGER.values())
        .where(Session.learner_id == learner_id)
        .order_by(Session.started_at.desc())
    )
    rows = (await db.execute(stmt)).scalars().all()
    return [SessionOut.from_model(row) for row in rows]


@router.post("", response_model=SessionOut, status_code=201)
async def create_session(
    payload: SessionCreate, db: AsyncSession = Depends(deps.get_db)
) -> SessionOut:
    learner = (
        await db.execute(select(Learner).where(Learner.id == payload.learner_id))
    ).scalar_one_or_none()
    if learner is None:
        raise HTTPException(status_code=404, detail=f"learner {payload.learner_id} not found")

    scenario_slug = payload.scenario_slug
    if payload.mode == SessionMode.scenario:
        if not scenario_slug:
            raise HTTPException(
                status_code=400, detail="scenario_slug is required when mode is 'scenario'"
            )
        scenario = (
            await db.execute(select(Scenario).where(Scenario.slug == scenario_slug))
        ).scalar_one_or_none()
        if scenario is None:
            raise HTTPException(
                status_code=404, detail=f"scenario '{scenario_slug}' not found"
            )
    else:
        scenario_slug = None

    provider = settings.llm_provider
    model = settings.ollama_model if provider == "ollama" else settings.openrouter_model
    session = Session(
        learner_id=learner.id,
        mode=payload.mode,
        scenario_slug=scenario_slug,
        llm_provider=provider,
        llm_model=model,
    )
    db.add(session)
    await db.commit()
    return SessionOut.from_model(session, turns=[])


@router.get("/{session_id}", response_model=SessionOut)
async def get_session(
    session_id: int,
    learner_id: int | None = Query(default=None),
    db: AsyncSession = Depends(deps.get_db),
) -> SessionOut:
    return SessionOut.from_model(await _get_session(db, session_id, learner_id))


@router.post("/{session_id}/end", response_model=SessionOut)
async def end_session(
    session_id: int, db: AsyncSession = Depends(deps.get_db)
) -> SessionOut:
    session = await _get_session(db, session_id)
    if session.ended_at is None:
        session.ended_at = datetime.now(UTC)
        await db.commit()
    return SessionOut.from_model(await _get_session(db, session_id))