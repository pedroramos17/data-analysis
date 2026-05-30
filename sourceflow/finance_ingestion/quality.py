"""Financial data quality checks."""

from __future__ import annotations

from collections.abc import Mapping


def market_bar_quality_flags(row: Mapping[str, object]) -> list[str]:
    """Return quality flags for an OHLCV row.

    Example:
        `flags = market_bar_quality_flags(row)`
    """
    flags: list[str] = []
    _append_missing_price_flags(row, flags)
    _append_ohlc_order_flags(row, flags)
    return flags


def _append_missing_price_flags(row: Mapping[str, object], flags: list[str]) -> None:
    if row.get("close") in (None, ""):
        flags.append("missing_close")
    if row.get("timestamp") in (None, ""):
        flags.append("missing_timestamp")


def _append_ohlc_order_flags(row: Mapping[str, object], flags: list[str]) -> None:
    high = _number(row.get("high"))
    low = _number(row.get("low"))
    if high is not None and low is not None and high < low:
        flags.append("high_below_low")


def _number(value: object) -> float | None:
    if value in (None, ""):
        return None
    return float(value)
