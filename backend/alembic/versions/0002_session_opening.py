"""record the opening line used by each session

Revision ID: 0002_session_opening
Revises: 0001_initial
Create Date: 2026-11-16
"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0002_session_opening"
down_revision: str | None = "0001_initial"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("session", sa.Column("opening_line", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("session", "opening_line")