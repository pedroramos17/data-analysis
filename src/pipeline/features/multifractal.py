"""Multifractal proxy feature group."""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence

from src.pipeline.features.base import (
    feature_row,
    float_or_none,
    group_symbol_timeframe,
    rolling_mean,
    rolling_std,
    rolling_values,
    safe_div,
)

FEATURE_SET = "multifractal"
FEATURE_COLUMNS = (
    "rolling_generalized_hurst_proxy",
    "mf_dfa",
    "spectrum_width_proxy",
    "intermittency_proxy",
    "scaling_exponent",
    "multifractal_volatility_proxy",
    "market_inefficiency_proxy",
)


def compute_multifractal_features(
    rows: Sequence[Mapping[str, object]],
    *,
    version: str,
    short_window: int = 20,
    long_window: int = 60,
) -> list[dict[str, object]]:
    """Compute deterministic multifractal proxies from past returns."""
    output: list[dict[str, object]] = []
    for group_rows in group_symbol_timeframe(rows).values():
        closes = [float_or_none(row.get("close")) for row in group_rows]
        returns = _log_returns(closes)
        for index, row in enumerate(group_rows):
            short_abs = rolling_mean([abs_value(value) for value in returns], index, short_window)
            long_abs = rolling_mean([abs_value(value) for value in returns], index, long_window)
            short_vol = rolling_std(returns, index, short_window)
            long_vol = rolling_std(returns, index, long_window)
            second = _moment(returns, index, short_window, 2)
            fourth = _moment(returns, index, short_window, 4)
            momentum = _momentum(closes, index, min(5, short_window))
            spectrum_width = _abs_diff(long_vol, short_vol)
            values = {
                "rolling_generalized_hurst_proxy": _hurst_proxy(short_abs, long_abs),
                "mf_dfa": safe_div(short_vol, long_vol),
                "spectrum_width_proxy": spectrum_width,
                "intermittency_proxy": safe_div(fourth, second * second if second is not None else None),
                "scaling_exponent": _scaling_exponent(short_vol, long_vol, short_window, long_window),
                "multifractal_volatility_proxy": _multifractal_volatility(returns[index], spectrum_width),
                "market_inefficiency_proxy": safe_div(abs(momentum) if momentum is not None else None, short_vol),
            }
            output.append(feature_row(row, FEATURE_SET, version, values))
    return output


def multifractal_sql(version: str) -> str:
    """Return DuckDB SQL sketch for multifractal proxies."""
    return f"""
    select
        'multifractal' as feature_set,
        '{version}' as version,
        symbol,
        asset_type,
        ts,
        timeframe,
        0.5 + avg(abs(log_return)) over w20 - avg(abs(log_return)) over w60 as rolling_generalized_hurst_proxy,
        stddev_samp(log_return) over w20 / nullif(stddev_samp(log_return) over w60, 0) as mf_dfa,
        abs(stddev_samp(log_return) over w60 - stddev_samp(log_return) over w20) as spectrum_width_proxy,
        avg(pow(log_return, 4)) over w20 / nullif(pow(avg(pow(log_return, 2)) over w20, 2), 0) as intermittency_proxy,
        ln(nullif(stddev_samp(log_return) over w20, 0) / nullif(stddev_samp(log_return) over w60, 0)) / ln(20.0 / 60.0) as scaling_exponent,
        abs(log_return) * abs(stddev_samp(log_return) over w60 - stddev_samp(log_return) over w20) as multifractal_volatility_proxy,
        abs(close / nullif(lag(close, 5) over w, 0) - 1) / nullif(stddev_samp(log_return) over w20, 0) as market_inefficiency_proxy
    from input_returns
    window
        w as (partition by symbol, timeframe order by ts),
        w20 as (partition by symbol, timeframe order by ts rows between 19 preceding and current row),
        w60 as (partition by symbol, timeframe order by ts rows between 59 preceding and current row)
    """.strip()


def abs_value(value: float | None) -> float | None:
    return abs(value) if value is not None else None


def _log_returns(closes: Sequence[float | None]) -> list[float | None]:
    output: list[float | None] = []
    previous: float | None = None
    for close in closes:
        if close is not None and previous not in (None, 0) and close > 0 and previous > 0:
            output.append(math.log(close / previous))
        else:
            output.append(None)
        if close is not None:
            previous = close
    return output


def _moment(values: Sequence[float | None], index: int, window: int, power: int) -> float | None:
    items = rolling_values(values, index, window)
    if not items:
        return None
    return sum(item**power for item in items) / len(items)


def _momentum(closes: Sequence[float | None], index: int, lag: int) -> float | None:
    close = closes[index]
    lag_close = closes[index - lag] if index >= lag else None
    if close is None or lag_close in (None, 0):
        return None
    return close / lag_close - 1.0


def _hurst_proxy(short_abs: float | None, long_abs: float | None) -> float | None:
    if short_abs is None or long_abs is None:
        return None
    return max(0.0, min(1.0, 0.5 + short_abs - long_abs))


def _abs_diff(left: float | None, right: float | None) -> float | None:
    if left is None or right is None:
        return None
    return abs(left - right)


def _scaling_exponent(
    short_vol: float | None,
    long_vol: float | None,
    short_window: int,
    long_window: int,
) -> float | None:
    if short_vol in (None, 0) or long_vol in (None, 0):
        return None
    return math.log(short_vol / long_vol) / math.log(short_window / long_window)


def _multifractal_volatility(value: float | None, spectrum_width: float | None) -> float | None:
    if value is None or spectrum_width is None:
        return None
    return abs(value) * spectrum_width
