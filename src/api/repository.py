"""Compatibility database reads for API endpoints."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field

from src.config.settings import DatabaseSettings


@dataclass(frozen=True, slots=True)
class RepositoryResult:
    """Small API repository result with optional warning text."""

    items: list[dict[str, object]] = field(default_factory=list)
    warning: str = ""

    def to_dict(self) -> dict[str, object]:
        payload: dict[str, object] = {"items": self.items}
        if self.warning:
            payload["warning"] = self.warning
        return payload


def list_assets(settings: DatabaseSettings, limit: int = 100) -> RepositoryResult:
    """List compatibility assets without exposing SQLite/Postgres details."""
    return _select_rows(settings, "assets", limit=limit)


def list_signals(settings: DatabaseSettings, limit: int = 100) -> RepositoryResult:
    """List compatibility signals without exposing SQLite/Postgres details."""
    return _select_rows(settings, "signals", limit=limit)


def get_backtest(settings: DatabaseSettings, run_id: int) -> RepositoryResult:
    """Fetch one compatibility backtest run."""
    return _select_rows(settings, "backtest_runs", row_id=run_id, limit=1)


def get_risk(settings: DatabaseSettings, run_id: int) -> RepositoryResult:
    """Fetch one compatibility risk run."""
    return _select_rows(settings, "risk_runs", row_id=run_id, limit=1)


def _select_rows(
    settings: DatabaseSettings,
    table_name: str,
    *,
    row_id: int | None = None,
    limit: int = 100,
) -> RepositoryResult:
    try:
        from sqlalchemy import MetaData, Table, create_engine, select

        from src.database.core_schema import sqlalchemy_url_from_database_settings
    except ImportError as exc:
        return RepositoryResult(warning=f"sqlalchemy unavailable: {exc}")

    engine = create_engine(sqlalchemy_url_from_database_settings(settings))
    try:
        metadata = MetaData()
        table = Table(table_name, metadata, autoload_with=engine)
        statement = select(table).limit(max(0, min(int(limit), 500)))
        if row_id is not None:
            statement = select(table).where(table.c.id == row_id).limit(1)
        with engine.connect() as connection:
            rows = [dict(row._mapping) for row in connection.execute(statement)]
    except Exception as exc:
        return RepositoryResult(warning=f"{table_name} unavailable: {exc}")
    finally:
        engine.dispose()
    return RepositoryResult(items=[_json_row(row) for row in rows])


def _json_row(row: Mapping[str, object]) -> dict[str, object]:
    return {str(key): _json_value(value) for key, value in row.items()}


def _json_value(value: object) -> object:
    if isinstance(value, str | int | float | bool) or value is None:
        return value
    if isinstance(value, dict):
        return {str(key): _json_value(item) for key, item in value.items()}
    if isinstance(value, list | tuple):
        return [_json_value(item) for item in value]
    return str(value)
