"""add feature run metadata table

Revision ID: 20260604_0003
Revises: 20260604_0002
Create Date: 2026-06-04
"""

from __future__ import annotations

from alembic import op
from sqlalchemy import inspect

from src.database.core_schema import feature_runs

revision = "20260604_0003"
down_revision = "20260604_0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Create the feature run metadata table if it is missing."""
    bind = op.get_bind()
    if "feature_runs" not in inspect(bind).get_table_names():
        feature_runs.create(bind=bind, checkfirst=True)


def downgrade() -> None:
    """Keep feature run metadata on downgrade to avoid data loss."""
