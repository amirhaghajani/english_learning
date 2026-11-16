"""initial schema for emma

Revision ID: 0001_initial
Revises:
Create Date: 2026-11-16
"""
from collections.abc import Sequence

import app.models  # noqa: F401
from alembic import op
from app.db import Base

revision: str = "0001_initial"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    Base.metadata.create_all(bind=bind)

    if bind.dialect.name == "postgresql":
        op.execute("ALTER TABLE curriculum_doc ADD COLUMN IF NOT EXISTS embedding vector(1024)")


def downgrade() -> None:
    bind = op.get_bind()
    Base.metadata.drop_all(bind=bind)