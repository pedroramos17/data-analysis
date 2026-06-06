"""Shared helpers for Phase 5 feature extraction."""

from __future__ import annotations

import json
import math
import sqlite3
import time
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from glob import glob
from pathlib import Path
from statistics import fmean

from src.config.settings import DatabaseSettings
from src.pipeline.ingestion.source_base import read_local_rows
from src.pipeline.ingestion.validators import rows_to_parquet_bytes
from src.storage.manifest import content_hash


@dataclass(frozen=True, slots=True)
class FeatureRunRecord:
    """Metadata row for one feature-set output."""

    feature_set: str
    version: str
    input_uri: str
    output_uri: str
    config_json: dict[str, object]
    rows: int
    columns: int
    started_at: datetime
    finished_at: datetime
    status: str
    error_json: dict[str, object] = field(default_factory=dict)
    id: int | None = None

    def to_dict(self) -> dict[str, object]:
        """Return a JSON-safe metadata payload."""
        return {
            "id": self.id,
            "feature_set": self.feature_set,
            "version": self.version,
            "input_uri": self.input_uri,
            "output_uri": self.output_uri,
            "config_json": dict(self.config_json),
            "rows": self.rows,
            "columns": self.columns,
            "started_at": self.started_at.astimezone(UTC).isoformat(),
            "finished_at": self.finished_at.astimezone(UTC).isoformat(),
            "status": self.status,
            "error_json": dict(self.error_json),
        }


@dataclass(frozen=True, slots=True)
class RuntimeMetrics:
    """Runtime, memory, and throughput metrics."""

    runtime_seconds: float
    memory_mb: float
    row_throughput_per_second: float

    def to_dict(self) -> dict[str, object]:
        """Return metric values rounded for stable JSON output."""
        return {
            "runtime_seconds": round(self.runtime_seconds, 6),
            "memory_mb": round(self.memory_mb, 6),
            "row_throughput_per_second": round(self.row_throughput_per_second, 6),
        }


class RuntimeTimer:
    """Simple deterministic runtime metric helper."""

    def __init__(self) -> None:
        self._start = time.perf_counter()

    def finish(self, rows: int) -> RuntimeMetrics:
        """Return elapsed runtime and current process memory."""
        elapsed = max(time.perf_counter() - self._start, 0.000001)
        return RuntimeMetrics(elapsed, _memory_mb(), rows / elapsed)


def read_feature_input_rows(
    path: str | Path,
    *,
    require_duckdb: bool = False,
) -> tuple[list[dict[str, object]], str, str]:
    """Read feature input rows from Parquet files without pandas."""
    files = _parquet_files(path)
    input_uri = str(Path(path))
    try:
        return _read_with_duckdb(files), "duckdb", input_uri
    except Exception as exc:
        if require_duckdb:
            raise RuntimeError("DuckDB feature input read failed") from exc
        return _read_with_local_fallback(files), "local_fallback", input_uri


def write_feature_rows(
    storage: object,
    feature_set: str,
    version: str,
    rows: Sequence[Mapping[str, object]],
) -> list[dict[str, object]]:
    """Write feature rows partitioned by feature_set/version/symbol/timeframe."""
    outputs: list[dict[str, object]] = []
    for (symbol, timeframe), group_rows in sorted(_group_symbol_timeframe(rows).items()):
        path = feature_output_path(feature_set, version, symbol, timeframe)
        data = rows_to_parquet_bytes(normalize_rows(group_rows))
        uri = storage.put_bytes(path, data, "application/vnd.apache.parquet")
        outputs.append(
            {
                "feature_set": feature_set,
                "version": version,
                "symbol": symbol,
                "timeframe": timeframe,
                "path": path,
                "uri": uri,
                "rows": len(group_rows),
                "columns": len(group_rows[0]) if group_rows else 0,
                "content_hash": content_hash(data),
            }
        )
    return outputs


def feature_output_path(feature_set: str, version: str, symbol: str, timeframe: str) -> str:
    """Return the required Phase 5 feature output key."""
    return (
        f"features/feature_set={token(feature_set)}/version={token(version)}/"
        f"symbol={token(symbol)}/timeframe={token(timeframe)}/part-000.parquet"
    )


def register_feature_run(
    database_settings: DatabaseSettings,
    record: FeatureRunRecord,
) -> int | None:
    """Register a feature run in SQLite or Postgres."""
    if database_settings.db_mode == "sqlite":
        return _register_sqlite(database_settings, record)
    return _register_sqlalchemy(database_settings, record)


def normalize_input_rows(rows: Sequence[Mapping[str, object]]) -> list[dict[str, object]]:
    """Normalize common feature input columns."""
    output: list[dict[str, object]] = []
    for row in rows:
        item = {str(key): value for key, value in dict(row).items()}
        item["symbol"] = str(item.get("symbol") or "UNKNOWN").upper()
        item["asset_type"] = str(item.get("asset_type") or "equity")
        item["timeframe"] = str(item.get("timeframe") or "1d")
        item["source"] = str(item.get("source") or "features")
        item["ts"] = timestamp(item.get("ts")).isoformat()
        for column in NUMERIC_COLUMNS:
            if column in item:
                item[column] = float_or_none(item.get(column))
        output.append(item)
    return sorted(output, key=sort_key)


def normalize_rows(rows: Sequence[Mapping[str, object]]) -> list[dict[str, object]]:
    """Return deterministic JSON-safe feature rows."""
    safe = [{str(key): json_safe(value) for key, value in dict(row).items()} for row in rows]
    return sorted(safe, key=sort_key)


def feature_row(
    base_row: Mapping[str, object],
    feature_set: str,
    version: str,
    values: Mapping[str, object],
) -> dict[str, object]:
    """Return one wide feature row."""
    return {
        "feature_set": feature_set,
        "version": version,
        "symbol": str(base_row.get("symbol") or ""),
        "asset_type": str(base_row.get("asset_type") or ""),
        "ts": str(base_row.get("ts") or ""),
        "timeframe": str(base_row.get("timeframe") or ""),
        **{key: json_safe(value) for key, value in values.items()},
        "source": "phase5_feature_pipeline",
    }


def group_symbol_timeframe(rows: Sequence[Mapping[str, object]]) -> dict[tuple[str, str], list[dict[str, object]]]:
    """Group rows by symbol/timeframe in deterministic order."""
    grouped: dict[tuple[str, str], list[dict[str, object]]] = {}
    for row in normalize_input_rows(rows):
        key = (str(row.get("symbol") or ""), str(row.get("timeframe") or ""))
        grouped.setdefault(key, []).append(dict(row))
    return {key: sorted(value, key=sort_key) for key, value in grouped.items()}


def rolling_values(values: Sequence[float | None], index: int, window: int) -> list[float]:
    """Return past-only rolling values ending at index."""
    start = max(0, index - window + 1)
    return [float(value) for value in values[start : index + 1] if value is not None]


def rolling_mean(values: Sequence[float | None], index: int, window: int) -> float | None:
    items = rolling_values(values, index, window)
    return fmean(items) if items else None


def rolling_std(values: Sequence[float | None], index: int, window: int) -> float | None:
    items = rolling_values(values, index, window)
    if len(items) < 2:
        return None
    mean = fmean(items)
    return math.sqrt(sum((item - mean) ** 2 for item in items) / (len(items) - 1))


def rolling_min(values: Sequence[float | None], index: int, window: int) -> float | None:
    items = rolling_values(values, index, window)
    return min(items) if items else None


def rolling_max(values: Sequence[float | None], index: int, window: int) -> float | None:
    items = rolling_values(values, index, window)
    return max(items) if items else None


def rolling_quantile(values: Sequence[float | None], index: int, window: int, q: float) -> float | None:
    items = sorted(rolling_values(values, index, window))
    if not items:
        return None
    position = min(max(int(math.floor(q * (len(items) - 1))), 0), len(items) - 1)
    return items[position]


def safe_div(numerator: object, denominator: object) -> float | None:
    """Return a safe float division."""
    left = float_or_none(numerator)
    right = float_or_none(denominator)
    if left is None or right in (None, 0.0):
        return None
    return left / right


def float_or_none(value: object) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def timestamp(value: object) -> datetime:
    parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def sort_key(row: Mapping[str, object]) -> tuple[str, str, str, str]:
    return (
        str(row.get("symbol") or ""),
        str(row.get("timeframe") or ""),
        str(row.get("ts") or ""),
        str(row.get("feature_set") or ""),
    )


def token(value: str) -> str:
    text = "".join(char if char.isalnum() or char in "-_" else "_" for char in str(value))
    return text.strip("_") or "__null__"


def json_safe(value: object) -> object:
    if isinstance(value, datetime):
        return value.astimezone(UTC).isoformat()
    if isinstance(value, Mapping):
        return {str(key): json_safe(item) for key, item in value.items()}
    if isinstance(value, list | tuple):
        return [json_safe(item) for item in value]
    if isinstance(value, str | int | float | bool) or value is None:
        return value
    return str(value)


def _parquet_files(path: str | Path) -> list[Path]:
    target = Path(path)
    if target.is_file() and target.suffix == ".parquet":
        return [target]
    if target.is_dir():
        files = sorted(Path(match) for match in glob(str(target / "**" / "*.parquet"), recursive=True))
        if files:
            return files
    raise FileNotFoundError(f"No feature input Parquet files found at {target}")


def _read_with_duckdb(files: Sequence[Path]) -> list[dict[str, object]]:
    import duckdb

    relation = _duckdb_relation(files)
    connection = duckdb.connect(":memory:")
    try:
        connection.execute("set timezone='UTC'")
        result = connection.execute(f"select * from {relation}")
        columns = [column[0] for column in result.description or []]
        return [dict(zip(columns, row, strict=False)) for row in result.fetchall()]
    finally:
        connection.close()


def _read_with_local_fallback(files: Sequence[Path]) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for path in files:
        partitions = _partitions_from_path(path)
        for row in read_local_rows(path):
            rows.append(partitions | dict(row))
    return rows


def _duckdb_relation(files: Sequence[Path]) -> str:
    values = ", ".join("'" + path.as_posix().replace("'", "''") + "'" for path in files)
    return f"read_parquet([{values}], hive_partitioning=true, union_by_name=true)"


def _partitions_from_path(path: Path) -> dict[str, object]:
    partitions: dict[str, object] = {}
    for part in path.parts:
        if "=" in part:
            key, value = part.split("=", 1)
            partitions[key] = value
    return partitions


def _group_symbol_timeframe(rows: Sequence[Mapping[str, object]]) -> dict[tuple[str, str], list[dict[str, object]]]:
    grouped: dict[tuple[str, str], list[dict[str, object]]] = {}
    for row in normalize_rows(rows):
        key = (str(row.get("symbol") or ""), str(row.get("timeframe") or ""))
        grouped.setdefault(key, []).append(dict(row))
    return grouped


def _register_sqlite(database_settings: DatabaseSettings, record: FeatureRunRecord) -> int:
    database_settings.sqlite_path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(database_settings.sqlite_path) as connection:
        _ensure_sqlite_feature_runs(connection)
        connection.execute(
            """
            DELETE FROM feature_runs
            WHERE status = 'COMPLETED'
              AND feature_set = ?
              AND version = ?
              AND output_uri = ?
            """,
            (record.feature_set, record.version, record.output_uri),
        )
        cursor = connection.execute(
            """
            INSERT INTO feature_runs (
                feature_set, version, input_uri, output_uri, config_json,
                rows, columns, started_at, finished_at, status, error_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                record.feature_set,
                record.version,
                record.input_uri,
                record.output_uri,
                json.dumps(record.config_json, sort_keys=True),
                record.rows,
                record.columns,
                record.started_at.astimezone(UTC).isoformat(),
                record.finished_at.astimezone(UTC).isoformat(),
                record.status,
                json.dumps(record.error_json, sort_keys=True),
            ),
        )
        return int(cursor.lastrowid)


def _register_sqlalchemy(database_settings: DatabaseSettings, record: FeatureRunRecord) -> int | None:
    try:
        from sqlalchemy import create_engine, delete, insert

        from src.database.core_schema import (
            create_core_tables,
            feature_runs,
            sqlalchemy_url_from_database_settings,
        )
    except ImportError as exc:
        raise RuntimeError("SQLAlchemy is required for Postgres feature run metadata") from exc
    engine = create_engine(sqlalchemy_url_from_database_settings(database_settings))
    try:
        with engine.begin() as connection:
            create_core_tables(connection)
            connection.execute(
                delete(feature_runs).where(
                    feature_runs.c.status == "COMPLETED",
                    feature_runs.c.feature_set == record.feature_set,
                    feature_runs.c.version == record.version,
                    feature_runs.c.output_uri == record.output_uri,
                )
            )
            result = connection.execute(
                insert(feature_runs).values(
                    feature_set=record.feature_set,
                    version=record.version,
                    input_uri=record.input_uri,
                    output_uri=record.output_uri,
                    config_json=record.config_json,
                    rows=record.rows,
                    columns=record.columns,
                    started_at=record.started_at,
                    finished_at=record.finished_at,
                    status=record.status,
                    error_json=record.error_json,
                )
            )
            primary_key = result.inserted_primary_key
            return int(primary_key[0]) if primary_key else None
    finally:
        engine.dispose()


def _ensure_sqlite_feature_runs(connection: sqlite3.Connection) -> None:
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS feature_runs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            feature_set TEXT NOT NULL,
            version TEXT NOT NULL,
            input_uri TEXT NOT NULL DEFAULT '',
            output_uri TEXT NOT NULL DEFAULT '',
            config_json TEXT NOT NULL DEFAULT '{}',
            rows INTEGER NOT NULL DEFAULT 0,
            columns INTEGER NOT NULL DEFAULT 0,
            started_at TEXT NOT NULL,
            finished_at TEXT,
            status TEXT NOT NULL,
            error_json TEXT NOT NULL DEFAULT '{}'
        )
        """
    )
    connection.execute(
        "CREATE INDEX IF NOT EXISTS ix_feature_runs_set_version "
        "ON feature_runs (feature_set, version)"
    )
    connection.execute(
        "CREATE INDEX IF NOT EXISTS ix_feature_runs_output_uri "
        "ON feature_runs (output_uri)"
    )


def _memory_mb() -> float:
    try:
        import resource
    except ImportError:
        return 0.0
    usage = float(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss)
    return usage / 1024.0


NUMERIC_COLUMNS = (
    "open",
    "high",
    "low",
    "close",
    "volume",
    "bid_price_1",
    "bid_size_1",
    "ask_price_1",
    "ask_size_1",
    "spread",
    "mid_price",
    "microprice",
    "depth_imbalance",
    "order_imbalance",
    "queue_pressure",
    "bid_ask_slope",
    "rolling_volatility",
    "realized_volatility",
)
