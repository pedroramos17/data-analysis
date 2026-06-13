"""Deterministic quality flag generation and outlier detection."""

from __future__ import annotations

from collections.abc import Mapping, Sequence

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


def detect_outliers(
    rows: Sequence[Mapping[str, object]],
    *,
    price_jump_threshold: float = 0.2,
    stale_periods: int = 2,
) -> list[dict[str, object]]:
    """Set quality flags using only current and previous observations."""
    output: list[dict[str, object]] = []
    previous_close: dict[tuple[str, str], float] = {}
    stale_counts: dict[tuple[str, str], int] = {}
    for row in sorted(rows, key=_sort_key):
        item = dict(row)
        key = (str(item.get("symbol") or ""), str(item.get("timeframe") or ""))
        close = _float_or_none(item.get("close"))
        previous = previous_close.get(key)
        if close is not None and previous not in (None, 0):
            jump = abs(close / previous - 1.0)
            item["price_jump"] = bool(item.get("price_jump", False) or jump > price_jump_threshold)
            if close == previous:
                stale_counts[key] = stale_counts.get(key, 0) + 1
            else:
                stale_counts[key] = 0
            item["stale_price"] = bool(
                item.get("stale_price", False) or stale_counts.get(key, 0) >= stale_periods
            )
        elif close is not None:
            stale_counts[key] = 0
        if close is not None:
            previous_close[key] = close
        volume = _float_or_none(item.get("volume"))
        item["zero_volume"] = bool(item.get("zero_volume", False) or volume == 0)
        item["invalid_spread"] = bool(item.get("invalid_spread", False) or _invalid_spread(item))
        item["incomplete_lob"] = bool(item.get("incomplete_lob", False) or _incomplete_lob(item))
        for flag in QUALITY_FLAGS:
            item[flag] = bool(item.get(flag, False))
        item["quality_flags"] = [flag for flag in QUALITY_FLAGS if item.get(flag)]
        output.append(item)
    return output


def quality_report(rows: Sequence[Mapping[str, object]]) -> dict[str, object]:
    """Aggregate deterministic quality flag counts."""
    counts = {flag: 0 for flag in QUALITY_FLAGS}
    for row in rows:
        for flag in QUALITY_FLAGS:
            if row.get(flag):
                counts[flag] += 1
    return {
        "rows": len(rows),
        "flag_counts": counts,
        "symbols": sorted({str(row.get("symbol") or "") for row in rows if row.get("symbol")}),
        "min_timestamp": min((str(row.get("ts")) for row in rows), default=""),
        "max_timestamp": max((str(row.get("ts")) for row in rows), default=""),
    }


def _invalid_spread(row: Mapping[str, object]) -> bool:
    high = _float_or_none(row.get("high"))
    low = _float_or_none(row.get("low"))
    close = _float_or_none(row.get("close"))
    bid = _float_or_none(row.get("bid_price_1"))
    ask = _float_or_none(row.get("ask_price_1"))
    if high is not None and low is not None and high < low:
        return True
    if close is not None and high is not None and close > high:
        return True
    if close is not None and low is not None and close < low:
        return True
    return bid is not None and ask is not None and ask <= bid


def _incomplete_lob(row: Mapping[str, object]) -> bool:
    has_lob_field = any(field in row for field in ("bid_price_1", "bid_size_1", "ask_price_1", "ask_size_1"))
    if not has_lob_field:
        return False
    return any(row.get(field) in (None, "") for field in ("bid_price_1", "bid_size_1", "ask_price_1", "ask_size_1"))


def _float_or_none(value: object) -> float | None:
    if value is None or value == "":
        return None
    return float(value)


def _sort_key(row: Mapping[str, object]) -> tuple[str, str, str]:
    return (
        str(row.get("symbol") or ""),
        str(row.get("timeframe") or ""),
        str(row.get("ts") or ""),
    )
