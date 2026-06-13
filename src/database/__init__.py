"""Database compatibility helpers for SQLite and Postgres runtime modes."""

from __future__ import annotations

from src.database.core_schema import (
    CORE_TABLE_NAMES,
    CORE_TABLES,
    build_core_engine,
    create_core_tables,
    drop_core_tables,
    metadata,
    sqlalchemy_url_from_database_settings,
)

__all__ = [
    "CORE_TABLE_NAMES",
    "CORE_TABLES",
    "build_core_engine",
    "create_core_tables",
    "drop_core_tables",
    "metadata",
    "sqlalchemy_url_from_database_settings",
]
