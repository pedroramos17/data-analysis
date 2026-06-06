"""Column and type cleaning for raw market data."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import UTC, datetime

from src.pipeline.ingestion.validators import normalize_timestamp

CANONICAL_ALIASES = {
    "datetime": "ts",
    "timestamp": "ts",
    "date": "ts",
    "time": "ts",
    "ticker": "symbol",
    "asset_symbol": "symbol",
    "open_price": "open",
    "high_price": "high",
    "low_price": "low",
    "close_price": "close",
    "adjusted_close": "close",
    "size": "volume",
}
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
)
QUALITY_FLAGS = (
    "missing_ohlcv",
    "stale_price",
    "zero_volume",
    "price_jump",
    "invalid_spread",
    "incomplete_lob",
    "timezone_adjusted",
    "imputed",
)


def clean_rows(rows: Sequence[Mapping[str, object]]) -> list[dict[str, object]]:
    """Clean column names, normalize timestamps, and coerce numeric values."""
    cleaned = [_clean_row(row) for row in rows]
    return sorted(cleaned, key=lambda row: (str(row.get("symbol") or ""), str(row.get("ts") or "")))


def clean_column_name(value: object) -> str:
    """Return a canonical snake_case column name."""
    normalized = "".join(char.lower() if char.isalnum() else "_" for char in str(value))
    normalized = "_".join(part for part in normalized.split("_") if part)
    return CANONICAL_ALIASES.get(normalized, normalized)


def _clean_row(row: Mapping[str, object]) -> dict[str, object]:
    item: dict[str, object] = {}
    original_timestamp: object = None
    for key, value in row.items():
        raw_name = "".join(char.lower() if char.isalnum() else "_" for char in str(key))
        raw_name = "_".join(part for part in raw_name.split("_") if part)
        name = clean_column_name(key)
        if name == "ts" and "ts" in item and raw_name == "date":
            continue
        if name == "ts":
            original_timestamp = value
        item[name] = value
    timestamp = normalize_timestamp(item.get("ts"))
    item["ts"] = timestamp.astimezone(UTC).isoformat()
    item["timezone_adjusted"] = _timezone_adjusted(original_timestamp, item["ts"])
    item["symbol"] = str(item.get("symbol") or "UNKNOWN").upper()
    item["asset_type"] = str(item.get("asset_type") or "equity")
    item["timeframe"] = str(item.get("timeframe") or "1d")
    item["source"] = str(item.get("source") or "unknown")
    for column in NUMERIC_COLUMNS:
        if column in item:
            item[column] = _float_or_none(item.get(column))
    for flag in QUALITY_FLAGS:
        item[flag] = bool(item.get(flag, False))
    return item


def _timezone_adjusted(original: object, normalized: object) -> bool:
    if isinstance(original, datetime):
        return original.tzinfo is not None and original.astimezone(UTC).isoformat() != str(original)
    text = str(original or "")
    return text.endswith("Z") or "+" in text[10:] or "-" in text[10:]


def _float_or_none(value: object) -> float | None:
    if value is None or (isinstance(value, str) and not value.strip()):
        return None
    return float(value)
