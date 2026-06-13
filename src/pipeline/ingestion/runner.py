"""Idempotent ingestion runner and metadata registration."""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

from src.config.settings import DatabaseSettings, load_runtime_settings
from src.pipeline.ingestion.lob_data import LobDataSource
from src.pipeline.ingestion.market_data import MarketDataSource
from src.pipeline.ingestion.news_data import NewsDataSource
from src.pipeline.ingestion.source_base import IngestionSource, SourceAsset
from src.pipeline.ingestion.validators import (
    deduplicate_rows,
    min_max_timestamp,
    missing_ratio,
    normalize_rows,
    rows_by_date,
    rows_to_parquet_bytes,
    schema_from_rows,
    validate_local_ingestion_path,
    validate_rows,
)
from src.providers.registry import ProviderRegistry, build_provider_registry
from src.storage.artifact_store import DataLakeArtifactStore


@dataclass(slots=True)
class IngestionRunRecord:
    """Metadata row for one raw ingestion partition."""

    source: str
    asset_type: str
    symbol: str
    timeframe: str
    start_ts: datetime | None
    end_ts: datetime | None
    status: str
    rows_written: int
    rows_deduplicated: int
    missing_ratio: float
    output_uri: str
    content_hash: str
    started_at: datetime
    finished_at: datetime | None = None
    error_json: dict[str, object] = field(default_factory=dict)
    stats_json: dict[str, object] = field(default_factory=dict)
    id: int | None = None

    def to_dict(self) -> dict[str, object]:
        """Return a JSON-serializable representation."""
        return {
            "id": self.id,
            "source": self.source,
            "asset_type": self.asset_type,
            "symbol": self.symbol,
            "timeframe": self.timeframe,
            "start_ts": _iso(self.start_ts),
            "end_ts": _iso(self.end_ts),
            "status": self.status,
            "rows_written": self.rows_written,
            "rows_deduplicated": self.rows_deduplicated,
            "missing_ratio": self.missing_ratio,
            "output_uri": self.output_uri,
            "content_hash": self.content_hash,
            "started_at": _iso(self.started_at),
            "finished_at": _iso(self.finished_at),
            "error_json": dict(self.error_json),
            "stats_json": dict(self.stats_json),
        }


@dataclass(frozen=True, slots=True)
class IngestionPipelineResult:
    """Top-level ingestion run summary."""

    status: str
    source: str
    assets: list[dict[str, object]]
    runs: list[IngestionRunRecord]
    errors: list[dict[str, object]] = field(default_factory=list)

    def to_dict(self) -> dict[str, object]:
        """Return a JSON-serializable summary."""
        return {
            "status": self.status,
            "source": self.source,
            "assets": self.assets,
            "runs": [run.to_dict() for run in self.runs],
            "errors": [dict(error) for error in self.errors],
            "rows_written": sum(run.rows_written for run in self.runs),
            "rows_deduplicated": sum(run.rows_deduplicated for run in self.runs),
        }


def run_ingestion(
    config: Mapping[str, object],
    registry: ProviderRegistry | None = None,
) -> IngestionPipelineResult:
    """Run the idempotent ingestion pipeline from a config mapping."""
    active_registry = registry or build_provider_registry(load_runtime_settings())
    source = build_ingestion_source(config)
    store = DataLakeArtifactStore(active_registry.get_storage())
    runs: list[IngestionRunRecord] = []
    errors: list[dict[str, object]] = []

    try:
        assets = source.discover_assets()
    except Exception as exc:
        record = _failed_record(config, source.name, None, exc, datetime.now(UTC))
        record.id = register_ingestion_run(active_registry.settings.database, record)
        return IngestionPipelineResult("FAILED", source.name, [], [record], [record.error_json])

    for asset in assets:
        started_at = datetime.now(UTC)
        try:
            runs.extend(_ingest_asset(active_registry, store, source, asset, started_at))
        except Exception as exc:
            record = _failed_record(config, source.name, asset, exc, started_at)
            record.id = register_ingestion_run(active_registry.settings.database, record)
            runs.append(record)
            errors.append(record.error_json)

    status = _result_status(runs, errors)
    return IngestionPipelineResult(status, source.name, [_asset_dict(asset) for asset in assets], runs, errors)


def validate_ingestion_path(path: str | Path) -> dict[str, object]:
    """Validate local raw ingestion files."""
    return validate_local_ingestion_path(Path(path))


def build_ingestion_source(config: Mapping[str, object]) -> IngestionSource:
    """Build a concrete source from config without network access by default."""
    source_type = str(
        config.get("source_type")
        or config.get("kind")
        or config.get("data_type")
        or ""
    ).lower()
    source_name = str(config.get("source") or "sample").lower()
    if source_type == "news" or source_name in {"news", "sample_news", "mock_news"}:
        return NewsDataSource(config)
    if source_type == "lob" or source_name in {"lob", "sample_lob", "mock_lob"}:
        return LobDataSource(config)
    return MarketDataSource(config)


def register_ingestion_run(
    database_settings: DatabaseSettings,
    record: IngestionRunRecord,
) -> int | None:
    """Register an ingestion run in SQLite or Postgres."""
    if database_settings.db_mode == "sqlite":
        return _register_sqlite(database_settings, record)
    return _register_sqlalchemy(database_settings, record)


def _ingest_asset(
    registry: ProviderRegistry,
    store: DataLakeArtifactStore,
    source: IngestionSource,
    asset: SourceAsset,
    started_at: datetime,
) -> list[IngestionRunRecord]:
    batch = source.fetch_raw_data(asset)
    validate_rows(batch.rows, source.schema_type)
    normalized = normalize_rows(
        batch.rows,
        schema_type=source.schema_type,
        source=source.name,
        asset_type=asset.asset_type,
        symbol=asset.symbol,
        timeframe=asset.timeframe,
    )
    original_by_date = rows_by_date(normalized)
    deduped, _duplicates = deduplicate_rows(normalized)
    deduped_by_date = rows_by_date(deduped)
    records: list[IngestionRunRecord] = []
    for date_key, rows in sorted(deduped_by_date.items()):
        data = rows_to_parquet_bytes(rows)
        saved = store.save_raw_data(
            source.name,
            asset.asset_type,
            asset.symbol,
            asset.timeframe,
            date_key,
            "part-000.parquet",
            data,
            schema=schema_from_rows(rows),
            row_count=len(rows),
            source=source.name,
        )
        start_ts, end_ts = min_max_timestamp(rows)
        record = IngestionRunRecord(
            source=source.name,
            asset_type=asset.asset_type,
            symbol=asset.symbol,
            timeframe=asset.timeframe,
            start_ts=start_ts,
            end_ts=end_ts,
            status="COMPLETED",
            rows_written=len(rows),
            rows_deduplicated=max(len(original_by_date.get(date_key, [])) - len(rows), 0),
            missing_ratio=missing_ratio(rows),
            output_uri=saved.object.uri,
            content_hash=saved.manifest.content_hash,
            started_at=started_at,
            finished_at=datetime.now(UTC),
            stats_json={
                "object_path": saved.object.path,
                "manifest_path": saved.object.manifest_path,
                "schema_type": source.schema_type,
                "raw_rows": len(original_by_date.get(date_key, [])),
            },
        )
        record.id = register_ingestion_run(registry.settings.database, record)
        records.append(record)
    return records


def _register_sqlite(database_settings: DatabaseSettings, record: IngestionRunRecord) -> int:
    database_settings.sqlite_path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(database_settings.sqlite_path) as connection:
        _ensure_sqlite_ingestion_runs(connection)
        columns = _sqlite_columns(connection)
        _delete_existing_success(connection, record, columns)
        values = _record_values(record, columns, sqlite=True)
        cursor = connection.execute(
            f"INSERT INTO ingestion_runs ({', '.join(values)}) VALUES ({_placeholders(values)})",
            tuple(values.values()),
        )
        return int(cursor.lastrowid)


def _register_sqlalchemy(database_settings: DatabaseSettings, record: IngestionRunRecord) -> int | None:
    try:
        from sqlalchemy import create_engine, delete, inspect, insert

        from src.database.core_schema import (
            create_core_tables,
            ingestion_runs,
            sqlalchemy_url_from_database_settings,
        )
    except ImportError as exc:
        raise RuntimeError("SQLAlchemy is required for Postgres ingestion metadata") from exc

    engine = create_engine(sqlalchemy_url_from_database_settings(database_settings))
    try:
        with engine.begin() as connection:
            create_core_tables(connection)
            columns = {column["name"] for column in inspect(connection).get_columns("ingestion_runs")}
            if _can_delete_existing(columns, record):
                connection.execute(
                    delete(ingestion_runs).where(
                        ingestion_runs.c.status == "COMPLETED",
                        ingestion_runs.c.source == record.source,
                        ingestion_runs.c.asset_type == record.asset_type,
                        ingestion_runs.c.symbol == record.symbol,
                        ingestion_runs.c.timeframe == record.timeframe,
                        ingestion_runs.c.output_uri == record.output_uri,
                        ingestion_runs.c.content_hash == record.content_hash,
                    )
                )
            result = connection.execute(
                insert(ingestion_runs).values(**_record_values(record, columns, sqlite=False))
            )
            primary_key = result.inserted_primary_key
            return int(primary_key[0]) if primary_key else None
    finally:
        engine.dispose()


def _ensure_sqlite_ingestion_runs(connection: sqlite3.Connection) -> None:
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS ingestion_runs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            source TEXT NOT NULL,
            asset_type TEXT NOT NULL DEFAULT '',
            symbol TEXT NOT NULL DEFAULT '',
            timeframe TEXT NOT NULL DEFAULT '',
            start_ts TEXT,
            end_ts TEXT,
            status TEXT NOT NULL,
            rows_written INTEGER NOT NULL DEFAULT 0,
            rows_deduplicated INTEGER NOT NULL DEFAULT 0,
            missing_ratio REAL NOT NULL DEFAULT 0,
            output_uri TEXT NOT NULL DEFAULT '',
            content_hash TEXT NOT NULL DEFAULT '',
            started_at TEXT NOT NULL,
            finished_at TEXT,
            error_json TEXT NOT NULL DEFAULT '{}',
            stats_json TEXT NOT NULL DEFAULT '{}',
            error TEXT NOT NULL DEFAULT ''
        )
        """
    )
    columns = _sqlite_columns(connection)
    for name, ddl in _SQLITE_COLUMN_DDL.items():
        if name not in columns:
            connection.execute(f"ALTER TABLE ingestion_runs ADD COLUMN {name} {ddl}")
    connection.execute(
        "CREATE INDEX IF NOT EXISTS ix_ingestion_runs_source_started_at "
        "ON ingestion_runs (source, started_at)"
    )
    connection.execute(
        "CREATE INDEX IF NOT EXISTS ix_ingestion_runs_identity "
        "ON ingestion_runs (source, asset_type, symbol, timeframe)"
    )
    connection.execute(
        "CREATE INDEX IF NOT EXISTS ix_ingestion_runs_output_hash "
        "ON ingestion_runs (output_uri, content_hash)"
    )


def _sqlite_columns(connection: sqlite3.Connection) -> set[str]:
    return {row[1] for row in connection.execute("PRAGMA table_info(ingestion_runs)")}


def _delete_existing_success(
    connection: sqlite3.Connection,
    record: IngestionRunRecord,
    columns: set[str],
) -> None:
    if not _can_delete_existing(columns, record):
        return
    connection.execute(
        """
        DELETE FROM ingestion_runs
        WHERE status = 'COMPLETED'
          AND source = ?
          AND asset_type = ?
          AND symbol = ?
          AND timeframe = ?
          AND output_uri = ?
          AND content_hash = ?
        """,
        (
            record.source,
            record.asset_type,
            record.symbol,
            record.timeframe,
            record.output_uri,
            record.content_hash,
        ),
    )


def _can_delete_existing(columns: set[str], record: IngestionRunRecord) -> bool:
    needed = {"status", "source", "asset_type", "symbol", "timeframe", "output_uri", "content_hash"}
    return record.status == "COMPLETED" and needed.issubset(columns)


def _record_values(
    record: IngestionRunRecord,
    columns: set[str],
    *,
    sqlite: bool,
) -> dict[str, object]:
    all_values: dict[str, object] = {
        "source": record.source,
        "asset_type": record.asset_type,
        "symbol": record.symbol,
        "timeframe": record.timeframe,
        "start_ts": _db_datetime(record.start_ts, sqlite),
        "end_ts": _db_datetime(record.end_ts, sqlite),
        "status": record.status,
        "rows_written": record.rows_written,
        "rows_deduplicated": record.rows_deduplicated,
        "missing_ratio": record.missing_ratio,
        "output_uri": record.output_uri,
        "content_hash": record.content_hash,
        "started_at": _db_datetime(record.started_at, sqlite),
        "finished_at": _db_datetime(record.finished_at, sqlite),
        "error_json": _db_json(record.error_json, sqlite),
        "stats_json": _db_json(_stats_json(record), sqlite),
        "error": json.dumps(record.error_json, sort_keys=True) if record.error_json else "",
    }
    return {key: value for key, value in all_values.items() if key in columns}


def _failed_record(
    config: Mapping[str, object],
    source: str,
    asset: SourceAsset | None,
    exc: Exception,
    started_at: datetime,
) -> IngestionRunRecord:
    symbol = asset.symbol if asset else str(config.get("symbol") or "ALL")
    asset_type = asset.asset_type if asset else str(config.get("asset_type") or "")
    timeframe = asset.timeframe if asset else str(config.get("timeframe") or "")
    error_json = {"type": type(exc).__name__, "message": str(exc)}
    return IngestionRunRecord(
        source=source,
        asset_type=asset_type,
        symbol=symbol,
        timeframe=timeframe,
        start_ts=None,
        end_ts=None,
        status="FAILED",
        rows_written=0,
        rows_deduplicated=0,
        missing_ratio=0.0,
        output_uri="",
        content_hash="",
        started_at=started_at,
        finished_at=datetime.now(UTC),
        error_json=error_json,
        stats_json={"config_keys": sorted(str(key) for key in config)},
    )


def _result_status(runs: Sequence[IngestionRunRecord], errors: Sequence[Mapping[str, object]]) -> str:
    completed = any(run.status == "COMPLETED" for run in runs)
    failed = bool(errors) or any(run.status == "FAILED" for run in runs)
    if completed and failed:
        return "PARTIAL_FAILED"
    if failed:
        return "FAILED"
    return "COMPLETED"


def _asset_dict(asset: SourceAsset) -> dict[str, object]:
    return {
        "symbol": asset.symbol,
        "asset_type": asset.asset_type,
        "timeframe": asset.timeframe,
    }


def _stats_json(record: IngestionRunRecord) -> dict[str, object]:
    return dict(record.stats_json) | {
        "rows_written": record.rows_written,
        "rows_deduplicated": record.rows_deduplicated,
        "missing_ratio": record.missing_ratio,
        "output_uri": record.output_uri,
        "content_hash": record.content_hash,
    }


def _db_datetime(value: datetime | None, sqlite: bool) -> object:
    if value is None:
        return None
    return value.astimezone(UTC).isoformat() if sqlite else value


def _db_json(value: Mapping[str, object], sqlite: bool) -> object:
    return json.dumps(dict(value), sort_keys=True) if sqlite else dict(value)


def _iso(value: datetime | None) -> str:
    return value.astimezone(UTC).isoformat() if value else ""


def _placeholders(values: Mapping[str, object]) -> str:
    return ", ".join("?" for _ in values)


_SQLITE_COLUMN_DDL = {
    "asset_type": "TEXT NOT NULL DEFAULT ''",
    "symbol": "TEXT NOT NULL DEFAULT ''",
    "timeframe": "TEXT NOT NULL DEFAULT ''",
    "start_ts": "TEXT",
    "end_ts": "TEXT",
    "rows_written": "INTEGER NOT NULL DEFAULT 0",
    "rows_deduplicated": "INTEGER NOT NULL DEFAULT 0",
    "missing_ratio": "REAL NOT NULL DEFAULT 0",
    "output_uri": "TEXT NOT NULL DEFAULT ''",
    "content_hash": "TEXT NOT NULL DEFAULT ''",
    "error_json": "TEXT NOT NULL DEFAULT '{}'",
    "stats_json": "TEXT NOT NULL DEFAULT '{}'",
    "error": "TEXT NOT NULL DEFAULT ''",
    "started_at": "TEXT NOT NULL DEFAULT ''",
    "finished_at": "TEXT",
}
