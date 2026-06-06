"""Validation, normalization, dedupe, and serialization helpers for ingestion."""

from __future__ import annotations

import json
from collections.abc import Iterable, Mapping, Sequence
from datetime import UTC, date, datetime
from pathlib import Path

from src.pipeline.ingestion.source_base import read_local_rows

FALLBACK_PARQUET_PREFIX = b"INGESTION_FALLBACK_JSONL\n"
TIMESTAMP_FIELDS = ("ts", "timestamp", "time", "date", "published_at")
REQUIRED_FIELDS = {
    "market": ("symbol", "open", "high", "low", "close", "volume"),
    "news": ("symbol", "headline", "url"),
    "lob": ("symbol", "bid_price_1", "bid_size_1", "ask_price_1", "ask_size_1"),
}
NUMERIC_FIELDS = {
    "market": ("open", "high", "low", "close", "volume"),
    "lob": ("bid_price_1", "bid_size_1", "ask_price_1", "ask_size_1"),
}


class IngestionValidationError(ValueError):
    """Raised when source rows do not satisfy the ingestion schema."""


def validate_rows(rows: Sequence[Mapping[str, object]], schema_type: str) -> None:
    """Validate required fields and timestamp availability."""
    if not rows:
        raise IngestionValidationError("Ingestion returned no rows")
    required = REQUIRED_FIELDS.get(schema_type, REQUIRED_FIELDS["market"])
    for index, row in enumerate(rows):
        missing = [field for field in required if _is_missing(row.get(field))]
        if _timestamp_value(row) is None:
            missing.append("ts")
        if missing:
            raise IngestionValidationError(
                f"Invalid {schema_type} row {index}; missing required fields: "
                + ", ".join(sorted(set(missing)))
            )


def normalize_rows(
    rows: Sequence[Mapping[str, object]],
    *,
    schema_type: str,
    source: str,
    asset_type: str,
    symbol: str,
    timeframe: str,
) -> list[dict[str, object]]:
    """Normalize timestamps/timezones and fill standard partition columns."""
    normalized: list[dict[str, object]] = []
    for row in rows:
        item = {str(key): value for key, value in dict(row).items()}
        item["source"] = str(item.get("source") or source)
        item["asset_type"] = str(item.get("asset_type") or asset_type)
        item["symbol"] = str(item.get("symbol") or symbol).upper()
        item["timeframe"] = str(item.get("timeframe") or timeframe)
        item["ts"] = normalize_timestamp(_timestamp_value(item))
        for field in NUMERIC_FIELDS.get(schema_type, ()):  # keep news text untouched
            item[field] = _float_or_none(item.get(field))
        normalized.append(_json_safe_row(item))
    return sorted(normalized, key=lambda item: _sort_key(item))


def normalize_timestamp(value: object) -> datetime:
    """Return a timezone-aware UTC timestamp."""
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, date):
        parsed = datetime.combine(value, datetime.min.time())
    else:
        text = str(value or "").strip()
        if not text:
            raise IngestionValidationError("Missing timestamp value")
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def deduplicate_rows(
    rows: Sequence[Mapping[str, object]],
) -> tuple[list[dict[str, object]], int]:
    """Deduplicate rows by source, asset, symbol, timeframe, and timestamp."""
    seen: dict[tuple[str, str, str, str, str], dict[str, object]] = {}
    for row in rows:
        item = dict(row)
        seen.setdefault(_dedupe_key(item), item)
    deduped = sorted(seen.values(), key=lambda item: _sort_key(item))
    return deduped, max(len(rows) - len(deduped), 0)


def rows_by_date(
    rows: Sequence[Mapping[str, object]],
) -> dict[str, list[dict[str, object]]]:
    """Group rows by UTC date partition."""
    grouped: dict[str, list[dict[str, object]]] = {}
    for row in rows:
        ts = normalize_timestamp(row.get("ts"))
        grouped.setdefault(ts.date().isoformat(), []).append(dict(row))
    return grouped


def missing_ratio(rows: Sequence[Mapping[str, object]]) -> float:
    """Return missing-cell ratio across rows."""
    cells = 0
    missing = 0
    for row in rows:
        for value in row.values():
            cells += 1
            if _is_missing(value):
                missing += 1
    return round(missing / cells, 6) if cells else 0.0


def min_max_timestamp(rows: Sequence[Mapping[str, object]]) -> tuple[datetime | None, datetime | None]:
    """Return min/max UTC timestamps for rows."""
    timestamps = [normalize_timestamp(row.get("ts")) for row in rows]
    if not timestamps:
        return None, None
    return min(timestamps), max(timestamps)


def schema_from_rows(rows: Sequence[Mapping[str, object]]) -> list[dict[str, object]]:
    """Return simple schema metadata for a stored partition."""
    first = dict(rows[0]) if rows else {}
    return [{"name": key, "type": type(value).__name__} for key, value in first.items()]


def rows_to_parquet_bytes(rows: Sequence[Mapping[str, object]]) -> bytes:
    """Serialize rows as Parquet, falling back to deterministic JSONL locally."""
    safe_rows = [_json_safe_row(row) for row in rows]
    try:
        import pyarrow as pa
        import pyarrow.parquet as pq
    except ImportError:
        lines = [json.dumps(row, sort_keys=True, default=str) for row in safe_rows]
        return FALLBACK_PARQUET_PREFIX + ("\n".join(lines) + "\n").encode("utf-8")
    sink = pa.BufferOutputStream()
    pq.write_table(pa.Table.from_pylist(safe_rows), sink)
    return sink.getvalue().to_pybytes()


def validate_local_ingestion_path(path: Path) -> dict[str, object]:
    """Validate one local file or a directory of raw ingestion files."""
    files = _ingestion_files(path)
    summaries = [_validate_file(file_path) for file_path in files]
    return {
        "status": "VALID",
        "path": str(path),
        "files": len(files),
        "rows": sum(int(item["rows"]) for item in summaries),
        "missing_ratio": _weighted_missing_ratio(summaries),
        "min_timestamp": _min_timestamp(summaries),
        "max_timestamp": _max_timestamp(summaries),
        "file_summaries": summaries,
    }


def _validate_file(path: Path) -> dict[str, object]:
    rows = read_local_rows(path)
    schema_type = _schema_type_from_path(path, rows)
    validate_rows(rows, schema_type)
    normalized = normalize_rows(
        rows,
        schema_type=schema_type,
        source=_partition_value(path, "source", "unknown"),
        asset_type=_partition_value(path, "asset_type", "equity"),
        symbol=_partition_value(path, "symbol", str(rows[0].get("symbol") or "UNKNOWN")),
        timeframe=_partition_value(path, "timeframe", "1d"),
    )
    start_ts, end_ts = min_max_timestamp(normalized)
    return {
        "path": str(path),
        "rows": len(normalized),
        "missing_ratio": missing_ratio(normalized),
        "min_timestamp": start_ts.isoformat() if start_ts else "",
        "max_timestamp": end_ts.isoformat() if end_ts else "",
        "schema": schema_from_rows(normalized),
    }


def _ingestion_files(path: Path) -> list[Path]:
    if path.is_file():
        return [path]
    if path.is_dir():
        files = sorted(item for item in path.rglob("*.parquet") if item.is_file())
        if files:
            return files
    raise FileNotFoundError(f"No ingestion Parquet files found at {path}")


def _schema_type_from_path(path: Path, rows: Sequence[Mapping[str, object]]) -> str:
    asset_type = _partition_value(path, "asset_type", "").lower()
    if asset_type == "news" or (rows and "headline" in rows[0]):
        return "news"
    if rows and "bid_price_1" in rows[0]:
        return "lob"
    return "market"


def _partition_value(path: Path, key: str, default: str) -> str:
    prefix = f"{key}="
    for part in path.parts:
        if part.startswith(prefix):
            return part.removeprefix(prefix)
    return default


def _weighted_missing_ratio(summaries: Sequence[Mapping[str, object]]) -> float:
    rows = sum(int(summary["rows"]) for summary in summaries)
    if rows <= 0:
        return 0.0
    weighted = sum(float(summary["missing_ratio"]) * int(summary["rows"]) for summary in summaries)
    return round(weighted / rows, 6)


def _min_timestamp(summaries: Sequence[Mapping[str, object]]) -> str:
    values = [str(summary["min_timestamp"]) for summary in summaries if summary["min_timestamp"]]
    return min(values) if values else ""


def _max_timestamp(summaries: Sequence[Mapping[str, object]]) -> str:
    values = [str(summary["max_timestamp"]) for summary in summaries if summary["max_timestamp"]]
    return max(values) if values else ""


def _timestamp_value(row: Mapping[str, object]) -> object:
    for field in TIMESTAMP_FIELDS:
        value = row.get(field)
        if not _is_missing(value):
            return value
    return None


def _dedupe_key(row: Mapping[str, object]) -> tuple[str, str, str, str, str]:
    ts = normalize_timestamp(row.get("ts")).isoformat()
    return (
        str(row.get("source") or ""),
        str(row.get("asset_type") or ""),
        str(row.get("symbol") or ""),
        str(row.get("timeframe") or ""),
        ts,
    )


def _sort_key(row: Mapping[str, object]) -> tuple[str, str, str]:
    return (
        str(row.get("symbol") or ""),
        normalize_timestamp(row.get("ts")).isoformat(),
        json.dumps(_json_safe_row(row), sort_keys=True, default=str),
    )


def _json_safe_row(row: Mapping[str, object]) -> dict[str, object]:
    return {str(key): _json_safe(value) for key, value in row.items()}


def _json_safe(value: object) -> object:
    if isinstance(value, datetime):
        return value.astimezone(UTC).isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, Mapping):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, Iterable) and not isinstance(value, str | bytes):
        return [_json_safe(item) for item in value]
    if isinstance(value, str | int | float | bool) or value is None:
        return value
    return str(value)


def _float_or_none(value: object) -> float | None:
    if _is_missing(value):
        return None
    return float(value)


def _is_missing(value: object) -> bool:
    return value is None or (isinstance(value, str) and not value.strip())
