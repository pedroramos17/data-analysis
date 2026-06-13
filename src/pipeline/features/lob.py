"""Limit-order-book feature group."""

from __future__ import annotations

from collections.abc import Mapping, Sequence

from src.pipeline.features.base import (
    feature_row,
    float_or_none,
    group_symbol_timeframe,
    rolling_std,
    safe_div,
)

FEATURE_SET = "lob"
FEATURE_COLUMNS = (
    "spread",
    "mid_price",
    "microprice",
    "depth_imbalance",
    "order_imbalance",
    "queue_pressure",
    "bid_ask_slope",
    "short_horizon_volatility",
)


def compute_lob_features(
    rows: Sequence[Mapping[str, object]],
    *,
    version: str,
    window: int = 5,
) -> list[dict[str, object]]:
    """Compute LOB features when quote/depth fields are available."""
    output: list[dict[str, object]] = []
    for group_rows in group_symbol_timeframe(rows).values():
        mids = [_mid_price(row) for row in group_rows]
        mid_returns = _returns(mids)
        for index, row in enumerate(group_rows):
            bid = float_or_none(row.get("bid_price_1"))
            ask = float_or_none(row.get("ask_price_1"))
            bid_size = float_or_none(row.get("bid_size_1"))
            ask_size = float_or_none(row.get("ask_size_1"))
            spread = _spread(row, bid, ask)
            depth_sum = _sum_or_none(bid_size, ask_size)
            values = {
                "spread": spread,
                "mid_price": mids[index],
                "microprice": _microprice(bid, ask, bid_size, ask_size),
                "depth_imbalance": _imbalance(bid_size, ask_size),
                "order_imbalance": _imbalance(bid_size, ask_size),
                "queue_pressure": safe_div(bid_size, ask_size),
                "bid_ask_slope": safe_div(spread, depth_sum),
                "short_horizon_volatility": rolling_std(mid_returns, index, window),
            }
            if any(value is not None for value in values.values()):
                output.append(feature_row(row, FEATURE_SET, version, values))
    return output


def lob_sql(version: str, window: int = 5) -> str:
    """Return DuckDB SQL for LOB features."""
    return f"""
    select
        'lob' as feature_set,
        '{version}' as version,
        symbol,
        asset_type,
        ts,
        timeframe,
        ask_price_1 - bid_price_1 as spread,
        (bid_price_1 + ask_price_1) / 2 as mid_price,
        (bid_price_1 * ask_size_1 + ask_price_1 * bid_size_1) / nullif(bid_size_1 + ask_size_1, 0) as microprice,
        (bid_size_1 - ask_size_1) / nullif(bid_size_1 + ask_size_1, 0) as depth_imbalance,
        (bid_size_1 - ask_size_1) / nullif(bid_size_1 + ask_size_1, 0) as order_imbalance,
        bid_size_1 / nullif(ask_size_1, 0) as queue_pressure,
        (ask_price_1 - bid_price_1) / nullif(bid_size_1 + ask_size_1, 0) as bid_ask_slope,
        stddev_samp(ln(((bid_price_1 + ask_price_1) / 2) / nullif(lag((bid_price_1 + ask_price_1) / 2) over w, 0)))
            over (partition by symbol, timeframe order by ts rows between {window - 1} preceding and current row)
            as short_horizon_volatility
    from input_rows
    window w as (partition by symbol, timeframe order by ts)
    """.strip()


def _spread(row: Mapping[str, object], bid: float | None, ask: float | None) -> float | None:
    existing = float_or_none(row.get("spread"))
    if existing is not None:
        return existing
    if bid is None or ask is None:
        return None
    return ask - bid


def _mid_price(row: Mapping[str, object]) -> float | None:
    existing = float_or_none(row.get("mid_price"))
    if existing is not None:
        return existing
    bid = float_or_none(row.get("bid_price_1"))
    ask = float_or_none(row.get("ask_price_1"))
    if bid is not None and ask is not None:
        return (bid + ask) / 2.0
    return float_or_none(row.get("close"))


def _microprice(
    bid: float | None,
    ask: float | None,
    bid_size: float | None,
    ask_size: float | None,
) -> float | None:
    if None in (bid, ask, bid_size, ask_size):
        return None
    denominator = float(bid_size) + float(ask_size)
    if denominator == 0:
        return None
    return (float(bid) * float(ask_size) + float(ask) * float(bid_size)) / denominator


def _imbalance(left: float | None, right: float | None) -> float | None:
    if left is None or right is None or left + right == 0:
        return None
    return (left - right) / (left + right)


def _sum_or_none(left: float | None, right: float | None) -> float | None:
    if left is None or right is None:
        return None
    return left + right


def _returns(values: Sequence[float | None]) -> list[float | None]:
    output: list[float | None] = []
    previous: float | None = None
    for value in values:
        if value is not None and previous not in (None, 0):
            output.append(value / previous - 1.0)
        else:
            output.append(None)
        if value is not None:
            previous = value
    return output
