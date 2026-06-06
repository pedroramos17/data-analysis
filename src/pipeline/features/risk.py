"""Risk feature group."""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence

from src.pipeline.features.base import (
    feature_row,
    float_or_none,
    group_symbol_timeframe,
    rolling_max,
    rolling_min,
    rolling_quantile,
    rolling_values,
)

FEATURE_SET = "risk"
FEATURE_COLUMNS = (
    "var",
    "cvar",
    "max_drawdown",
    "rolling_beta",
    "rolling_correlation",
    "covariance_estimate",
    "tail_risk_flag",
)


def compute_risk_features(
    rows: Sequence[Mapping[str, object]],
    *,
    version: str,
    window: int = 60,
) -> list[dict[str, object]]:
    """Compute rolling risk features with past-only windows."""
    normalized_groups = group_symbol_timeframe(rows)
    market_returns = _market_returns(normalized_groups)
    output: list[dict[str, object]] = []
    for group_rows in normalized_groups.values():
        closes = [float_or_none(row.get("close")) for row in group_rows]
        returns = _simple_returns(closes)
        drawdowns = _drawdowns(closes, window)
        market = [market_returns.get((str(row.get("timeframe")), str(row.get("ts")))) for row in group_rows]
        for index, row in enumerate(group_rows):
            var_value = rolling_quantile(returns, index, window, 0.05)
            cvar_value = _cvar(returns, index, window, var_value)
            covariance = _covariance(returns, market, index, window)
            market_variance = _variance(market, index, window)
            correlation = _correlation(returns, market, index, window)
            values = {
                "var": var_value,
                "cvar": cvar_value,
                "max_drawdown": rolling_min(drawdowns, index, window),
                "rolling_beta": covariance / market_variance if market_variance not in (None, 0) and covariance is not None else None,
                "rolling_correlation": correlation,
                "covariance_estimate": covariance,
                "tail_risk_flag": 1.0 if var_value is not None and returns[index] is not None and returns[index] <= var_value else 0.0,
            }
            output.append(feature_row(row, FEATURE_SET, version, values))
    return output


def risk_sql(version: str, window: int = 60) -> str:
    """Return DuckDB SQL sketch for rolling risk features."""
    return f"""
    select
        'risk' as feature_set,
        '{version}' as version,
        symbol,
        asset_type,
        ts,
        timeframe,
        quantile_cont(simple_return, 0.05) over w_roll as var,
        avg(case when simple_return <= quantile_cont(simple_return, 0.05) over w_roll then simple_return else null end) over w_roll as cvar,
        min(drawdown) over w_roll as max_drawdown,
        covar_samp(simple_return, market_return) over w_roll / nullif(var_samp(market_return) over w_roll, 0) as rolling_beta,
        corr(simple_return, market_return) over w_roll as rolling_correlation,
        covar_samp(simple_return, market_return) over w_roll as covariance_estimate,
        case when simple_return <= quantile_cont(simple_return, 0.05) over w_roll then 1.0 else 0.0 end as tail_risk_flag
    from input_returns
    window w_roll as (partition by symbol, timeframe order by ts rows between {window - 1} preceding and current row)
    """.strip()


def _simple_returns(closes: Sequence[float | None]) -> list[float | None]:
    output: list[float | None] = []
    previous: float | None = None
    for close in closes:
        if close is not None and previous not in (None, 0):
            output.append(close / previous - 1.0)
        else:
            output.append(None)
        if close is not None:
            previous = close
    return output


def _drawdowns(closes: Sequence[float | None], window: int) -> list[float | None]:
    output: list[float | None] = []
    for index, close in enumerate(closes):
        peak = rolling_max(closes, index, window)
        if close is None or peak in (None, 0):
            output.append(None)
        else:
            output.append(close / peak - 1.0)
    return output


def _market_returns(groups: Mapping[tuple[str, str], Sequence[Mapping[str, object]]]) -> dict[tuple[str, str], float]:
    by_ts: dict[tuple[str, str], list[float]] = {}
    for group_rows in groups.values():
        returns = _simple_returns([float_or_none(row.get("close")) for row in group_rows])
        for row, value in zip(group_rows, returns, strict=False):
            if value is not None:
                key = (str(row.get("timeframe")), str(row.get("ts")))
                by_ts.setdefault(key, []).append(value)
    return {key: sum(values) / len(values) for key, values in by_ts.items() if values}


def _cvar(values: Sequence[float | None], index: int, window: int, var_value: float | None) -> float | None:
    if var_value is None:
        return None
    tail = [value for value in rolling_values(values, index, window) if value <= var_value]
    return sum(tail) / len(tail) if tail else None


def _covariance(left: Sequence[float | None], right: Sequence[float | None], index: int, window: int) -> float | None:
    pairs = _paired(left, right, index, window)
    if len(pairs) < 2:
        return None
    left_mean = sum(item[0] for item in pairs) / len(pairs)
    right_mean = sum(item[1] for item in pairs) / len(pairs)
    return sum((a - left_mean) * (b - right_mean) for a, b in pairs) / (len(pairs) - 1)


def _variance(values: Sequence[float | None], index: int, window: int) -> float | None:
    items = rolling_values(values, index, window)
    if len(items) < 2:
        return None
    mean = sum(items) / len(items)
    return sum((item - mean) ** 2 for item in items) / (len(items) - 1)


def _correlation(left: Sequence[float | None], right: Sequence[float | None], index: int, window: int) -> float | None:
    covariance = _covariance(left, right, index, window)
    left_var = _variance(left, index, window)
    right_var = _variance(right, index, window)
    if covariance is None or left_var in (None, 0) or right_var in (None, 0):
        return None
    return covariance / math.sqrt(left_var * right_var)


def _paired(
    left: Sequence[float | None],
    right: Sequence[float | None],
    index: int,
    window: int,
) -> list[tuple[float, float]]:
    start = max(0, index - window + 1)
    pairs: list[tuple[float, float]] = []
    for left_value, right_value in zip(left[start : index + 1], right[start : index + 1], strict=False):
        if left_value is not None and right_value is not None:
            pairs.append((float(left_value), float(right_value)))
    return pairs
