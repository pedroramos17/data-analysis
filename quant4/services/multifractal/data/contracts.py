"""Typed data contracts for Quant4 multifractal datasets."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

BAR_SCHEMA_VERSION = "quant4_multifractal_ohlcv_bars_v1"
RETURN_SCHEMA_VERSION = "quant4_multifractal_returns_v1"


@dataclass(frozen=True, slots=True)
class OHLCVBar:
    """Canonical OHLCV bar used by Quant4 multifractal analysis.

    Example:
        `OHLCVBar("SPY", "stock", None, ts, 1, 1, 1, 1, None, "USD", "csv", "1d", None)`
    """

    symbol: str
    asset_class: str | None
    exchange: str | None
    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float | None
    currency: str | None
    source: str
    timeframe: str
    adjusted_close: float | None


@dataclass(frozen=True, slots=True)
class ReturnRecord:
    """Derived return row generated from canonical OHLCV bars.

    Example:
        `ReturnRecord("SPY", ts, "1d", "close_to_close", "close", ...)`
    """

    symbol: str
    timestamp: datetime
    timeframe: str
    return_type: str
    price_col: str
    log_return: float
    simple_return: float
    abs_return: float
    squared_return: float
    realized_volatility_optional: float | None
    source_dataset_id: str


@dataclass(frozen=True, slots=True)
class DatasetWriteResult:
    """Summary returned by local Parquet writes.

    Example:
        `DatasetWriteResult("data/root", ["data/root/part.parquet"], 10)`
    """

    root_path: str
    partition_paths: list[str]
    row_count: int
    schema_version: str


def bar_to_row(bar: OHLCVBar) -> dict[str, object]:
    """Convert an OHLCV bar into an Arrow-friendly row.

    Example:
        `row = bar_to_row(bar)`
    """
    return {
        "symbol": bar.symbol,
        "asset_class": bar.asset_class,
        "exchange": bar.exchange,
        "timestamp": bar.timestamp,
        "open": bar.open,
        "high": bar.high,
        "low": bar.low,
        "close": bar.close,
        "volume": bar.volume,
        "currency": bar.currency,
        "source": bar.source,
        "timeframe": bar.timeframe,
        "adjusted_close": bar.adjusted_close,
    }


def row_to_bar(row: dict[str, object]) -> OHLCVBar:
    """Convert an Arrow row into an OHLCV bar.

    Example:
        `bar = row_to_bar(row)`
    """
    return OHLCVBar(
        str(row["symbol"]),
        _optional_text(row.get("asset_class")),
        _optional_text(row.get("exchange")),
        _timestamp(row["timestamp"]),
        float(row["open"]),
        float(row["high"]),
        float(row["low"]),
        float(row["close"]),
        _optional_float(row.get("volume")),
        _optional_text(row.get("currency")),
        str(row["source"]),
        str(row["timeframe"]),
        _optional_float(row.get("adjusted_close")),
    )


def return_to_row(record: ReturnRecord) -> dict[str, object]:
    """Convert a return record into an Arrow-friendly row.

    Example:
        `row = return_to_row(record)`
    """
    return {
        "symbol": record.symbol,
        "timestamp": record.timestamp,
        "timeframe": record.timeframe,
        "return_type": record.return_type,
        "price_col": record.price_col,
        "log_return": record.log_return,
        "simple_return": record.simple_return,
        "abs_return": record.abs_return,
        "squared_return": record.squared_return,
        "realized_volatility_optional": record.realized_volatility_optional,
        "source_dataset_id": record.source_dataset_id,
    }


def row_to_return(row: dict[str, object]) -> ReturnRecord:
    """Convert an Arrow row into a return record.

    Example:
        `record = row_to_return(row)`
    """
    return ReturnRecord(
        str(row["symbol"]),
        _timestamp(row["timestamp"]),
        str(row["timeframe"]),
        str(row["return_type"]),
        str(row["price_col"]),
        float(row["log_return"]),
        float(row["simple_return"]),
        float(row["abs_return"]),
        float(row["squared_return"]),
        _optional_float(row.get("realized_volatility_optional")),
        str(row["source_dataset_id"]),
    )


def _timestamp(value: object) -> datetime:
    if isinstance(value, datetime):
        return value
    raise ValueError(f"Invalid timestamp {value!r}; expected datetime")


def _optional_text(value: object) -> str | None:
    if value is None or value == "":
        return None
    return str(value)


def _optional_float(value: object) -> float | None:
    if value is None or value == "":
        return None
    return float(value)
