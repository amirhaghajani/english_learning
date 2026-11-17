from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app import deps
from app.models import Learner
from app.schemas import LearnerCreate, LearnerOut, LearnerUpdate

router = APIRouter(prefix="/api/learners", tags=["learners"])


async def _get_or_404(db: AsyncSession, learner_id: int) -> Learner:
    learner = (
        await db.execute(select(Learner).where(Learner.id == learner_id))
    ).scalar_one_or_none()
    if learner is None:
        raise HTTPException(status_code=404, detail=f"learner {learner_id} not found")
    return learner


@router.get("", response_model=list[LearnerOut])
async def list_learners(db: AsyncSession = Depends(deps.get_db)) -> list[LearnerOut]:
    rows = (await db.execute(select(Learner).order_by(Learner.created_at))).scalars().all()
    return [LearnerOut.model_validate(row) for row in rows]


@router.post("", response_model=LearnerOut, status_code=201)
async def create_learner(
    payload: LearnerCreate, db: AsyncSession = Depends(deps.get_db)
) -> LearnerOut:
    existing = (
        await db.execute(select(Learner).where(Learner.name == payload.name))
    ).scalar_one_or_none()
    if existing is not None:
        raise HTTPException(status_code=409, detail=f"learner '{payload.name}' already exists")

    learner = Learner(
        name=payload.name,
        cefr=payload.cefr,
        native_lang=payload.native_lang,
        goals=payload.goals,
    )
    db.add(learner)
    await db.commit()
    return LearnerOut.model_validate(learner)


@router.patch("/{learner_id}", response_model=LearnerOut)
async def update_learner(
    learner_id: int, payload: LearnerUpdate, db: AsyncSession = Depends(deps.get_db)
) -> LearnerOut:
    learner = await _get_or_404(db, learner_id)
    data = payload.model_dump(exclude_unset=True)
    if "name" in data:
        clash = (
            await db.execute(
                select(Learner).where(Learner.name == data["name"], Learner.id != learner_id)
            )
        ).scalar_one_or_none()
        if clash is not None:
            raise HTTPException(status_code=409, detail=f"name '{data['name']}' is taken")
    for key, value in data.items():
        setattr(learner, key, value)
    await db.commit()
    return LearnerOut.model_validate(learner)


@router.get("/{learner_id}", response_model=LearnerOut)
async def get_learner(
    learner_id: int, db: AsyncSession = Depends(deps.get_db)
) -> LearnerOut:
    return LearnerOut.model_validate(await _get_or_404(db, learner_id))