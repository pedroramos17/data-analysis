"""Typed data contracts for Quant multifractal datasets."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime

from sourceflow.finance_core import BarRecord
from sourceflow.finance_core.schemas import BAR_SCHEMA_VERSION
from sourceflow.finance_core.time import require_datetime

RETURN_SCHEMA_VERSION = "quant_multifractal_returns_v1"

OHLCVBar = BarRecord


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


def bar_to_row(bar: BarRecord) -> dict[str, object]:
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


def row_to_bar(row: Mapping[str, object]) -> BarRecord:
    """Convert an Arrow row into an OHLCV bar.

    Example:
        `bar = row_to_bar(row)`
    """
    return BarRecord(
        symbol=str(row["symbol"]),
        asset_class=_optional_text(row.get("asset_class")),
        exchange=_optional_text(row.get("exchange")),
        timestamp=require_datetime(row["timestamp"], "timestamp"),
        open=float(row["open"]),
        high=float(row["high"]),
        low=float(row["low"]),
        close=float(row["close"]),
        volume=_optional_float(row.get("volume")),
        currency=_optional_text(row.get("currency")),
        source=str(row["source"]),
        timeframe=str(row["timeframe"]),
        adjusted_close=_optional_float(row.get("adjusted_close")),
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


def row_to_return(row: Mapping[str, object]) -> ReturnRecord:
    """Convert an Arrow row into a return record.

    Example:
        `record = row_to_return(row)`
    """
    return ReturnRecord(
        str(row["symbol"]),
        require_datetime(row["timestamp"], "timestamp"),
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


def _optional_text(value: object) -> str | None:
    if value is None or value == "":
        return None
    return str(value)


def _optional_float(value: object) -> float | None:
    if value is None or value == "":
        return None
    return float(value)
