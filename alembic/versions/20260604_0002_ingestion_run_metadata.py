"""add explicit ingestion run metadata columns

Revision ID: 20260604_0002
Revises: 20260602_0001
Create Date: 2026-06-04
"""

from __future__ import annotations

from alembic import op
from sqlalchemy import Column, DateTime, Float, Integer, String, inspect

from src.database.core_schema import CompatibleJSON

revision = "20260604_0002"
down_revision = "20260602_0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Add explicit ingestion metadata columns when missing."""
    bind = op.get_bind()
    existing = {column["name"] for column in inspect(bind).get_columns("ingestion_runs")}
    for column in _columns():
        if column.name not in existing:
            op.add_column("ingestion_runs", column)
    indexes = {index["name"] for index in inspect(bind).get_indexes("ingestion_runs")}
    if "ix_ingestion_runs_identity" not in indexes:
        op.create_index(
            "ix_ingestion_runs_identity",
            "ingestion_runs",
            ["source", "asset_type", "symbol", "timeframe"],
        )
    if "ix_ingestion_runs_output_hash" not in indexes:
        op.create_index(
            "ix_ingestion_runs_output_hash",
            "ingestion_runs",
            ["output_uri", "content_hash"],
        )


def downgrade() -> None:
    """Keep metadata columns on downgrade to avoid data loss."""


def _columns() -> list[Column[object]]:
    return [
        Column("asset_type", String(40), nullable=False, server_default=""),
        Column("symbol", String(64), nullable=False, server_default=""),
        Column("timeframe", String(32), nullable=False, server_default=""),
        Column("start_ts", DateTime(timezone=True), nullable=True),
        Column("end_ts", DateTime(timezone=True), nullable=True),
        Column("rows_written", Integer, nullable=False, server_default="0"),
        Column("rows_deduplicated", Integer, nullable=False, server_default="0"),
        Column("missing_ratio", Float, nullable=False, server_default="0"),
        Column("output_uri", String(1200), nullable=False, server_default=""),
        Column("content_hash", String(128), nullable=False, server_default=""),
        Column("error_json", CompatibleJSON(), nullable=False, server_default="{}"),
    ]
