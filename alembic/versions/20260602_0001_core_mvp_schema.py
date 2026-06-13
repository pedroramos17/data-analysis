"""create core mvp compatibility tables

Revision ID: 20260602_0001
Revises:
Create Date: 2026-06-02
"""

from __future__ import annotations

from alembic import op

from src.database.core_schema import CORE_TABLES, metadata

revision = "20260602_0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Create the MVP tables if they are missing."""
    bind = op.get_bind()
    metadata.create_all(bind=bind, tables=list(CORE_TABLES), checkfirst=True)


def downgrade() -> None:
    """Drop the MVP tables from isolated compatibility databases."""
    bind = op.get_bind()
    metadata.drop_all(bind=bind, tables=list(CORE_TABLES), checkfirst=True)
