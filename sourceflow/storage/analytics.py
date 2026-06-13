"""DuckDB analytics over a Parquet snapshot of the canonical tables.

This reads *only* the snapshot Parquet files, never the transactional Django
database -- so analytics queries are fully decoupled from ingestion and cannot
block writes. DuckDB scans Parquet columnar files, so aggregates over large
document/chunk tables stay efficient.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any


class AnalyticsError(RuntimeError):
    """Raised when the analytics layer cannot run (missing dep or snapshot)."""


def _valid_identifier(value: str) -> bool:
    return bool(re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", value))


class SourceflowAnalytics:
    """Read-only DuckDB analytics bound to a snapshot directory."""

    def __init__(self, snapshot_dir: str | Path) -> None:
        self.snapshot_dir = Path(snapshot_dir)
        self._connection: Any | None = None

    def _connect(self) -> Any:
        if self._connection is None:
            try:
                import duckdb
            except ImportError as exc:  # pragma: no cover - duckdb is a declared dep
                raise AnalyticsError("duckdb is required for analytics; expected installed module") from exc
            connection = duckdb.connect(":memory:")
            connection.execute("set timezone='UTC'")
            # Expose each snapshot Parquet file as a read-only view.
            for parquet in sorted(self.snapshot_dir.glob("*.parquet")):
                view = parquet.stem
                if not _valid_identifier(view):
                    continue
                connection.execute(
                    f'create or replace view "{view}" as '
                    f"select * from read_parquet('{parquet.as_posix()}')"
                )
            self._connection = connection
        return self._connection

    def close(self) -> None:
        if self._connection is not None:
            self._connection.close()
            self._connection = None

    def __enter__(self) -> "SourceflowAnalytics":
        self._connect()
        return self

    def __exit__(self, *args: object) -> None:
        self.close()

    def query(self, sql: str, params: list[Any] | None = None) -> list[dict[str, Any]]:
        result = self._connect().execute(sql, params or [])
        columns = [column[0] for column in result.description or []]
        return [dict(zip(columns, row)) for row in result.fetchall()]

    def scalar(self, sql: str, params: list[Any] | None = None) -> Any:
        row = self._connect().execute(sql, params or []).fetchone()
        return row[0] if row else None

    # -- canned analytics --------------------------------------------------

    def count(self, table: str) -> int:
        if not _valid_identifier(table):
            raise AnalyticsError(f"invalid table name: {table!r}")
        return int(self.scalar(f'select count(*) from "{table}"') or 0)

    def events_by_type(self) -> list[dict[str, Any]]:
        return self.query(
            'select event_type, count(*) as n from "events" group by event_type order by n desc, event_type'
        )

    def claims_by_source(self) -> list[dict[str, Any]]:
        return self.query(
            'select s.name as source, count(*) as claims '
            'from "claims" c join "sources" s on c.source_id = s.id '
            "group by s.name order by claims desc, source"
        )

    def chunk_stats(self) -> dict[str, Any]:
        rows = self.query(
            'select count(*) as chunks, coalesce(sum(token_count), 0) as tokens, '
            'coalesce(avg(token_count), 0) as avg_tokens from "chunks"'
        )
        return rows[0] if rows else {"chunks": 0, "tokens": 0, "avg_tokens": 0}

    def top_subjects(self, limit: int = 10) -> list[dict[str, Any]]:
        return self.query(
            'select e.canonical_name as entity, count(*) as claims '
            'from "claims" c join "entities" e on c.subject_entity_id = e.id '
            "group by e.canonical_name order by claims desc, entity limit ?",
            [int(limit)],
        )
