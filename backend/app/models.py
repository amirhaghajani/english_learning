from datetime import datetime
from enum import StrEnum

from sqlalchemy import (
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy import (
    Enum as SAEnum,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class CEFR(StrEnum):
    A1 = "A1"
    A2 = "A2"
    B1 = "B1"
    B2 = "B2"
    C1 = "C1"


class SessionMode(StrEnum):
    scenario = "scenario"
    free = "free"


class CorrectionCategory(StrEnum):
    grammar = "grammar"
    word_choice = "word_choice"
    naturalness = "naturalness"


class CorrectionSeverity(StrEnum):
    minor = "minor"
    major = "major"


class CurriculumKind(StrEnum):
    grammar = "grammar"
    usage = "usage"
    scenario = "scenario"


def _enum_col(enum_cls, **kwargs):
    return mapped_column(
        SAEnum(enum_cls, native_enum=False, length=32, validate_strings=True), **kwargs
    )


class Learner(Base):
    __tablename__ = "learner"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(120), unique=True, nullable=False)
    cefr: Mapped[CEFR] = _enum_col(CEFR, nullable=False, default=CEFR.B1)
    native_lang: Mapped[str] = mapped_column(String(80), nullable=False, default="en")
    goals: Mapped[str] = mapped_column(Text, nullable=False, default="")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    sessions: Mapped[list["Session"]] = relationship(
        back_populates="learner", cascade="all, delete-orphan"
    )


class Session(Base):
    __tablename__ = "session"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    learner_id: Mapped[int] = mapped_column(
        ForeignKey("learner.id", ondelete="CASCADE"), nullable=False, index=True
    )
    mode: Mapped[SessionMode] = _enum_col(SessionMode, nullable=False)
    scenario_slug: Mapped[str | None] = mapped_column(String(120), nullable=True)
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    llm_provider: Mapped[str | None] = mapped_column(String(40), nullable=True)
    llm_model: Mapped[str | None] = mapped_column(String(120), nullable=True)

    learner: Mapped[Learner] = relationship(back_populates="sessions")
    turns: Mapped[list["Turn"]] = relationship(
        back_populates="session", cascade="all, delete-orphan"
    )


class Turn(Base):
    __tablename__ = "turn"
    __table_args__ = (UniqueConstraint("session_id", "seq", name="uq_turn_session_seq"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    session_id: Mapped[int] = mapped_column(
        ForeignKey("session.id", ondelete="CASCADE"), nullable=False, index=True
    )
    seq: Mapped[int] = mapped_column(Integer, nullable=False)
    transcript: Mapped[str] = mapped_column(Text, nullable=False, default="")
    reply_text: Mapped[str] = mapped_column(Text, nullable=False, default="")
    audio_ms: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    no_speech: Mapped[bool] = mapped_column(default=False, nullable=False)
    abandoned_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    session: Mapped[Session] = relationship(back_populates="turns")
    corrections: Mapped[list["Correction"]] = relationship(
        back_populates="turn", cascade="all, delete-orphan"
    )


class Correction(Base):
    __tablename__ = "correction"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    turn_id: Mapped[int] = mapped_column(
        ForeignKey("turn.id", ondelete="CASCADE"), nullable=False, index=True
    )
    said: Mapped[str] = mapped_column(Text, nullable=False)
    replacement: Mapped[str] = mapped_column(Text, nullable=False)
    category: Mapped[CorrectionCategory] = _enum_col(CorrectionCategory, nullable=False)
    why: Mapped[str] = mapped_column(Text, nullable=False, default="")
    severity: Mapped[CorrectionSeverity] = _enum_col(
        CorrectionSeverity, nullable=False, default=CorrectionSeverity.minor
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    turn: Mapped[Turn] = relationship(back_populates="corrections")


class CurriculumDoc(Base):
    __tablename__ = "curriculum_doc"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    slug: Mapped[str] = mapped_column(String(160), unique=True, nullable=False)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    kind: Mapped[CurriculumKind] = _enum_col(CurriculumKind, nullable=False)
    level: Mapped[str] = mapped_column(String(8), nullable=False, default="A1")
    body: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class Scenario(Base):
    __tablename__ = "scenario"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    slug: Mapped[str] = mapped_column(String(120), unique=True, nullable=False)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    level: Mapped[str] = mapped_column(String(8), nullable=False, default="A1")
    setting: Mapped[str] = mapped_column(Text, nullable=False, default="")
    learner_role: Mapped[str] = mapped_column(Text, nullable=False, default="")
    emma_role: Mapped[str] = mapped_column(Text, nullable=False, default="")
    opening_line: Mapped[str] = mapped_column(Text, nullable=False, default="")
    target_language: Mapped[str] = mapped_column(Text, nullable=False, default="")
    success_criteria: Mapped[str] = mapped_column(Text, nullable=False, default="")