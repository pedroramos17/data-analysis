"""Price/volume feature group."""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence

from src.pipeline.features.base import (
    feature_row,
    float_or_none,
    group_symbol_timeframe,
    rolling_max,
    rolling_mean,
    rolling_std,
    safe_div,
)

FEATURE_SET = "price_volume"
FEATURE_COLUMNS = (
    "log_return",
    "simple_return",
    "rolling_mean",
    "rolling_volatility",
    "realized_volatility",
    "momentum",
    "mean_reversion",
    "rolling_zscore",
    "drawdown",
    "volume_zscore",
    "liquidity_proxy",
)


def compute_price_volume_features(
    rows: Sequence[Mapping[str, object]],
    *,
    version: str,
    window: int = 20,
    momentum_window: int = 5,
) -> list[dict[str, object]]:
    """Compute past-only price/volume features."""
    output: list[dict[str, object]] = []
    for group_rows in group_symbol_timeframe(rows).values():
        closes = [float_or_none(row.get("close")) for row in group_rows]
        volumes = [float_or_none(row.get("volume")) for row in group_rows]
        log_returns = _log_returns(closes)
        simple_returns = _simple_returns(closes)
        for index, row in enumerate(group_rows):
            close = closes[index]
            volume = volumes[index]
            mean_close = rolling_mean(closes, index, window)
            std_close = rolling_std(closes, index, window)
            rolling_vol = rolling_std(log_returns, index, window)
            realized_vol = _realized_volatility(log_returns, index, window)
            peak = rolling_max(closes, index, window)
            avg_volume = rolling_mean(volumes, index, window)
            std_volume = rolling_std(volumes, index, window)
            lag_close = closes[index - momentum_window] if index >= momentum_window else None
            values = {
                "log_return": log_returns[index],
                "simple_return": simple_returns[index],
                "rolling_mean": mean_close,
                "rolling_volatility": rolling_vol,
                "realized_volatility": realized_vol,
                "momentum": _momentum(close, lag_close),
                "mean_reversion": _mean_reversion(close, mean_close),
                "rolling_zscore": _zscore(close, mean_close, std_close),
                "drawdown": _drawdown(close, peak),
                "volume_zscore": _zscore(volume, avg_volume, std_volume),
                "liquidity_proxy": safe_div(volume, abs(simple_returns[index]) if simple_returns[index] is not None else None),
            }
            output.append(feature_row(row, FEATURE_SET, version, values))
    return output


def price_volume_sql(version: str, window: int = 20) -> str:
    """Return DuckDB SQL for the price/volume feature group."""
    return f"""
    select
        'price_volume' as feature_set,
        '{version}' as version,
        symbol,
        asset_type,
        ts,
        timeframe,
        ln(close / nullif(lag(close) over w, 0)) as log_return,
        close / nullif(lag(close) over w, 0) - 1 as simple_return,
        avg(close) over w_roll as rolling_mean,
        stddev_samp(ln(close / nullif(lag(close) over w, 0))) over w_roll as rolling_volatility,
        sqrt(avg(pow(ln(close / nullif(lag(close) over w, 0)), 2)) over w_roll) as realized_volatility,
        close / nullif(lag(close, 5) over w, 0) - 1 as momentum,
        avg(close) over w_roll / nullif(close, 0) - 1 as mean_reversion,
        (close - avg(close) over w_roll) / nullif(stddev_samp(close) over w_roll, 0) as rolling_zscore,
        close / nullif(max(close) over w_roll, 0) - 1 as drawdown,
        (volume - avg(volume) over w_roll) / nullif(stddev_samp(volume) over w_roll, 0) as volume_zscore,
        volume / nullif(abs(close / nullif(lag(close) over w, 0) - 1), 0) as liquidity_proxy
    from input_rows
    window
        w as (partition by symbol, timeframe order by ts),
        w_roll as (partition by symbol, timeframe order by ts rows between {window - 1} preceding and current row)
    """.strip()


def _log_returns(closes: Sequence[float | None]) -> list[float | None]:
    values: list[float | None] = []
    previous: float | None = None
    for close in closes:
        if close is not None and previous not in (None, 0) and close > 0 and previous > 0:
            values.append(math.log(close / previous))
        else:
            values.append(None)
        if close is not None:
            previous = close
    return values


def _simple_returns(closes: Sequence[float | None]) -> list[float | None]:
    values: list[float | None] = []
    previous: float | None = None
    for close in closes:
        if close is not None and previous not in (None, 0):
            values.append(close / previous - 1.0)
        else:
            values.append(None)
        if close is not None:
            previous = close
    return values


def _realized_volatility(values: Sequence[float | None], index: int, window: int) -> float | None:
    items = [item for item in values[max(0, index - window + 1) : index + 1] if item is not None]
    if not items:
        return None
    return math.sqrt(sum(item * item for item in items) / len(items))


def _momentum(close: float | None, lag_close: float | None) -> float | None:
    if close is None or lag_close in (None, 0):
        return None
    return close / lag_close - 1.0


def _mean_reversion(close: float | None, mean_close: float | None) -> float | None:
    if close is None or mean_close in (None, 0):
        return None
    return mean_close / close - 1.0


def _zscore(value: float | None, mean: float | None, std: float | None) -> float | None:
    if value is None or mean is None or std in (None, 0):
        return None
    return (value - mean) / std


def _drawdown(close: float | None, peak: float | None) -> float | None:
    if close is None or peak in (None, 0):
        return None
    return close / peak - 1.0
