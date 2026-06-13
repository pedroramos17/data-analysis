"""Validation and CSV import for multifractal market data."""

from __future__ import annotations

import csv
import math
from collections.abc import Iterable, Mapping
from datetime import UTC, datetime
from pathlib import Path

from quant.services.multifractal.data.contracts import ReturnRecord
from sourceflow.finance_core import BarRecord

OHLCVBar = BarRecord

PRICE_COLUMNS = ("open", "high", "low", "close")


def import_ohlcv_csv(
    path: Path,
    symbol: str,
    asset_class: str | None,
    timeframe: str,
    source: str,
) -> list[OHLCVBar]:
    """Import a local OHLCV CSV into canonical bar records.

    Example:
        `bars = import_ohlcv_csv(Path("spy.csv"), "SPY", "stock", "1d", "csv")`
    """
    with path.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    bars = [
        _bar_from_csv_row(row, symbol, asset_class, timeframe, source)
        for row in rows
    ]
    return validate_ohlcv_bars(bars)


def validate_ohlcv_bars(bars: Iterable[OHLCVBar]) -> list[OHLCVBar]:
    """Validate canonical bars and return timestamp-ordered records.

    Example:
        `valid_bars = validate_ohlcv_bars(bars)`
    """
    records = list(bars)
    _require_non_empty(records)
    _validate_required_prices(records)
    _validate_timestamp_order_and_uniqueness(records)
    return sorted(records, key=_bar_sort_key)


def generate_return_records(
    bars: Iterable[OHLCVBar],
    price_col: str = "close",
    return_type: str = "close_to_close",
    source_dataset_id: str = "",
) -> list[ReturnRecord]:
    """Generate no-lookahead return rows from adjacent bar prices.

    Example:
        `returns = generate_return_records(bars, price_col="close")`
    """
    validated = validate_ohlcv_bars(bars)
    _validate_price_column(price_col)
    return [
        _return_record(previous, current, price_col, return_type, source_dataset_id)
        for previous, current in zip(validated, validated[1:], strict=False)
    ]


def _bar_from_csv_row(
    row: Mapping[str, object],
    symbol: str,
    asset_class: str | None,
    timeframe: str,
    source: str,
) -> OHLCVBar:
    return BarRecord(
        symbol=symbol,
        asset_class=asset_class,
        exchange=_optional_text(row.get("exchange")),
        timestamp=_parse_timestamp(row.get("timestamp")),
        open=_positive_float(row.get("open"), "open"),
        high=_positive_float(row.get("high"), "high"),
        low=_positive_float(row.get("low"), "low"),
        close=_positive_float(row.get("close"), "close"),
        volume=_optional_float(row.get("volume"), "volume"),
        currency=_optional_text(row.get("currency")),
        source=source,
        timeframe=timeframe,
        adjusted_close=_optional_positive_float(
            row.get("adjusted_close"),
            "adjusted_close",
        ),
    )


def _parse_timestamp(value: object) -> datetime:
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(f"Invalid timestamp {value!r}; expected ISO datetime") from exc
    return parsed.astimezone(UTC)


def _positive_float(value: object, label: str) -> float:
    parsed = _required_float(value, label)
    if parsed > 0:
        return parsed
    raise ValueError(f"Invalid {label} {value!r}; expected positive float")


def _required_float(value: object, label: str) -> float:
    if value in (None, ""):
        raise ValueError(f"Invalid {label} {value!r}; expected required float")
    try:
        parsed = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"Invalid {label} {value!r}; expected float") from exc
    return _finite_float(parsed, label, value)


def _optional_positive_float(value: object, label: str) -> float | None:
    if value in (None, ""):
        return None
    return _positive_float(value, label)


def _optional_float(value: object, label: str) -> float | None:
    if value in (None, ""):
        return None
    parsed = _required_float(value, label)
    if parsed >= 0:
        return parsed
    raise ValueError(f"Invalid {label} {value!r}; expected non-negative float")


def _finite_float(parsed: float, label: str, value: object) -> float:
    if math.isfinite(parsed):
        return parsed
    raise ValueError(f"Invalid {label} {value!r}; expected finite float")


def _optional_text(value: object) -> str | None:
    if value in (None, ""):
        return None
    return str(value)


def _bar_sort_key(bar: OHLCVBar) -> tuple[str, str, datetime]:
    return bar.symbol, bar.timeframe, bar.timestamp


def _require_non_empty(bars: list[OHLCVBar]) -> None:
    if bars:
        return
    raise ValueError("Invalid OHLCV bars []; expected at least one row")


def _validate_required_prices(bars: list[OHLCVBar]) -> None:
    for bar in bars:
        _validate_high_low_relationship(bar)
        for label in PRICE_COLUMNS:
            _positive_float(getattr(bar, label), label)


def _validate_high_low_relationship(bar: OHLCVBar) -> None:
    if bar.high >= max(bar.open, bar.close) and bar.low <= min(bar.open, bar.close):
        return
    raise ValueError(
        f"Invalid OHLCV bar {bar!r}; expected high/low to bound open and close"
    )


def _validate_timestamp_order_and_uniqueness(bars: list[OHLCVBar]) -> None:
    seen: set[tuple[str, str, datetime]] = set()
    for bar in bars:
        _validate_unique_timestamp(seen, bar)
    for previous, current in zip(bars, bars[1:], strict=False):
        _validate_timestamp_pair(previous, current)


def _validate_timestamp_pair(previous: OHLCVBar, current: OHLCVBar) -> None:
    if previous.symbol != current.symbol or previous.timeframe != current.timeframe:
        return
    if previous.timestamp < current.timestamp:
        return
    raise ValueError(
        f"Invalid timestamp order {(previous.timestamp, current.timestamp)!r}; "
        "expected strictly increasing timestamps"
    )


def _validate_unique_timestamp(
    seen: set[tuple[str, str, datetime]],
    bar: OHLCVBar,
) -> None:
    key = (bar.symbol, bar.timeframe, bar.timestamp)
    if key not in seen:
        seen.add(key)
        return
    raise ValueError(f"Invalid duplicate timestamp {key!r}; expected unique row")


def _validate_price_column(price_col: str) -> None:
    if price_col in PRICE_COLUMNS or price_col == "adjusted_close":
        return
    raise ValueError(f"Invalid price_col {price_col!r}; expected OHLCV price column")


def _return_record(
    previous: OHLCVBar,
    current: OHLCVBar,
    price_col: str,
    return_type: str,
    source_dataset_id: str,
) -> ReturnRecord:
    previous_price = _positive_float(getattr(previous, price_col), price_col)
    current_price = _positive_float(getattr(current, price_col), price_col)
    simple_return = (current_price / previous_price) - 1.0
    log_return = math.log(current_price / previous_price)
    return ReturnRecord(
        current.symbol,
        current.timestamp,
        current.timeframe,
        return_type,
        price_col,
        log_return,
        simple_return,
        abs(log_return),
        log_return * log_return,
        None,
        source_dataset_id,
    )
