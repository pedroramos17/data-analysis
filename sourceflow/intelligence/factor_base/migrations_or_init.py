"""Backward-compatible raw-SQL initialization for the factor registry."""

from __future__ import annotations

from collections.abc import Sequence
from importlib import resources


def upgrade_factor_schema(connection: object) -> None:
    """Create or upgrade factor registry tables.

    Example:
        `upgrade_factor_schema(connection)`
    """
    _execute_schema(connection)
    _ensure_columns(connection, "factors", _factor_columns())
    _ensure_columns(connection, "factor_values", _value_columns())
    _ensure_factor_runs(connection)


def _execute_schema(connection: object) -> None:
    for statement in _schema_statements():
        with connection.cursor() as cursor:
            cursor.execute(statement)


def _schema_statements() -> tuple[str, ...]:
    return tuple(
        statement.strip() for statement in _schema_sql().split(";") if statement.strip()
    )


def _schema_sql() -> str:
    schema_path = resources.files("sourceflow.intelligence.factor_base").joinpath(
        "schema.sql"
    )
    return schema_path.read_text(encoding="utf-8")


def _ensure_columns(
    connection: object,
    table_name: str,
    columns: Sequence[tuple[str, str]],
) -> None:
    existing = _table_columns(connection, table_name)
    for column_name, column_sql in columns:
        if column_name not in existing:
            _execute(connection, f"ALTER TABLE {table_name} ADD COLUMN {column_sql}")


def _table_columns(connection: object, table_name: str) -> set[str]:
    with connection.cursor() as cursor:
        cursor.execute(f"PRAGMA table_info({table_name})")
        return {str(row[1]) for row in cursor.fetchall()}


def _factor_columns() -> tuple[tuple[str, str], ...]:
    return (
        ("slug", "slug TEXT NOT NULL DEFAULT ''"),
        ("expression_text", "expression_text TEXT NOT NULL DEFAULT ''"),
        ("return_type", "return_type TEXT NOT NULL DEFAULT 'numeric'"),
        ("object_level", "object_level TEXT NOT NULL DEFAULT 'event'"),
        ("source", "source TEXT NOT NULL DEFAULT 'seed'"),
        ("max_depth", "max_depth INTEGER NOT NULL DEFAULT 0"),
        ("version", "version INTEGER NOT NULL DEFAULT 1"),
        ("notes", "notes TEXT NOT NULL DEFAULT ''"),
    )


def _value_columns() -> tuple[tuple[str, str], ...]:
    return (
        ("object_level", "object_level TEXT NOT NULL DEFAULT ''"),
        ("time_window_start", "time_window_start TEXT NOT NULL DEFAULT ''"),
        ("time_window_end", "time_window_end TEXT NOT NULL DEFAULT ''"),
        ("content_hash", "content_hash TEXT NOT NULL DEFAULT ''"),
    )


def _ensure_factor_runs(connection: object) -> None:
    sql = """
        CREATE TABLE IF NOT EXISTS factor_runs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            factor_name TEXT NOT NULL,
            run_started_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            run_finished_at TEXT NOT NULL DEFAULT '',
            status TEXT NOT NULL,
            row_count INTEGER NOT NULL DEFAULT 0,
            output_parquet_path TEXT NOT NULL DEFAULT '',
            error_message TEXT NOT NULL DEFAULT ''
        )
    """
    _execute(connection, sql)


def _execute(connection: object, sql: str) -> None:
    with connection.cursor() as cursor:
        cursor.execute(sql)
