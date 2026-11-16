from datetime import UTC, datetime

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.models import CEFR, CorrectionCategory, CorrectionSeverity, CurriculumKind, SessionMode


class UTCTimestampMixin(BaseModel):
    @model_validator(mode="after")
    def _normalise_timestamps(self):
        for name in type(self).model_fields:
            value = getattr(self, name, None)
            if isinstance(value, datetime):
                if value.tzinfo is None:
                    setattr(self, name, value.replace(tzinfo=UTC))
                else:
                    setattr(self, name, value.astimezone(UTC))
        return self


class LearnerCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    cefr: CEFR = CEFR.B1
    native_lang: str = Field(default="en", min_length=1, max_length=80)
    goals: str = ""


class LearnerUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    cefr: CEFR | None = None
    native_lang: str | None = Field(default=None, min_length=1, max_length=80)
    goals: str | None = None


class LearnerOut(UTCTimestampMixin):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    cefr: CEFR
    native_lang: str
    goals: str
    created_at: datetime


class CorrectionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    turn_id: int
    said: str
    replacement: str
    category: CorrectionCategory
    why: str
    severity: CorrectionSeverity


class TurnOut(UTCTimestampMixin):
    model_config = ConfigDict(from_attributes=True)

    id: int
    session_id: int
    seq: int
    transcript: str
    reply_text: str
    audio_ms: int
    no_speech: bool
    abandoned: bool = False
    created_at: datetime
    corrections: list[CorrectionOut] = []

    @classmethod
    def from_model(cls, turn) -> "TurnOut":  # noqa: ANN001
        return cls(
            id=turn.id,
            session_id=turn.session_id,
            seq=turn.seq,
            transcript=turn.transcript,
            reply_text=turn.reply_text,
            audio_ms=turn.audio_ms,
            no_speech=turn.no_speech,
            abandoned=turn.abandoned_at is not None,
            created_at=turn.created_at,
            corrections=[CorrectionOut.model_validate(c) for c in turn.corrections],
        )


class SessionOut(UTCTimestampMixin):
    model_config = ConfigDict(from_attributes=True)

    id: int
    learner_id: int
    mode: SessionMode
    scenario_slug: str | None
    started_at: datetime
    ended_at: datetime | None
    llm_provider: str | None
    llm_model: str | None
    turns: list[TurnOut] = []

    @classmethod
    def from_model(cls, session, turns: list | None = None) -> "SessionOut":  # noqa: ANN001
        return cls(
            id=session.id,
            learner_id=session.learner_id,
            mode=session.mode,
            scenario_slug=session.scenario_slug,
            started_at=session.started_at,
            ended_at=session.ended_at,
            llm_provider=session.llm_provider,
            llm_model=session.llm_model,
            turns=[TurnOut.from_model(t) for t in (turns if turns is not None else session.turns)],
        )


class ScenarioOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    slug: str
    title: str
    level: str
    setting: str
    learner_role: str
    emma_role: str
    opening_line: str
    target_language: str
    success_criteria: str


class SessionCreate(BaseModel):
    learner_id: int
    mode: SessionMode = SessionMode.free
    scenario_slug: str | None = None


class TurnAccepted(BaseModel):
    turn_id: int
    transcript: str
    no_speech: bool
    audio_ms: int


class HealthOut(BaseModel):
    status: str
    database: bool
    database_backend: str
    llm_provider: str
    llm_model: str
    llm_reachable: bool
    stt_backend: str
    stt_ready: bool
    tts_backend: str
    tts_ready: bool
    rag_backend: str
    details: dict[str, str] = {}


class IngestResult(BaseModel):
    documents: int
    upserted: int
    skipped: int
    embedded: int
    backend: str
    warnings: list[str] = []


class CurriculumOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    slug: str
    title: str
    kind: CurriculumKind
    level: str
    body: str