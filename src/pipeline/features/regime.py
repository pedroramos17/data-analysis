"""Regime feature group."""

from __future__ import annotations

from collections.abc import Mapping, Sequence

from src.pipeline.features.base import (
    feature_row,
    float_or_none,
    group_symbol_timeframe,
    rolling_mean,
    rolling_std,
    safe_div,
)

FEATURE_SET = "regime"
FEATURE_COLUMNS = (
    "trend_regime",
    "volatility_regime",
    "liquidity_regime",
    "correlation_regime",
    "multifractal_inefficiency_regime",
)


def compute_regime_features(
    rows: Sequence[Mapping[str, object]],
    *,
    version: str,
    window: int = 20,
) -> list[dict[str, object]]:
    """Compute regime labels from past-only rolling statistics."""
    groups = group_symbol_timeframe(rows)
    market_returns = _market_returns(groups)
    output: list[dict[str, object]] = []
    for group_rows in groups.values():
        closes = [float_or_none(row.get("close")) for row in group_rows]
        volumes = [float_or_none(row.get("volume")) for row in group_rows]
        returns = _simple_returns(closes)
        market = [market_returns.get((str(row.get("timeframe")), str(row.get("ts")))) for row in group_rows]
        for index, row in enumerate(group_rows):
            momentum = _momentum(closes, index, min(5, window))
            volatility = rolling_std(returns, index, window)
            long_volatility = rolling_std(returns, index, max(window * 3, window + 1))
            liquidity = rolling_mean(volumes, index, window)
            long_liquidity = rolling_mean(volumes, index, max(window * 3, window + 1))
            correlation = _correlation(returns, market, index, window)
            inefficiency = safe_div(abs(momentum) if momentum is not None else None, volatility)
            values = {
                "trend_regime": _sign(momentum),
                "volatility_regime": 1.0 if volatility is not None and long_volatility is not None and volatility > long_volatility else 0.0,
                "liquidity_regime": 1.0 if liquidity is not None and long_liquidity is not None and liquidity < long_liquidity else 0.0,
                "correlation_regime": 1.0 if correlation is not None and abs(correlation) > 0.6 else 0.0,
                "multifractal_inefficiency_regime": 1.0 if inefficiency is not None and inefficiency > 1.0 else 0.0,
            }
            output.append(feature_row(row, FEATURE_SET, version, values))
    return output


def regime_sql(version: str) -> str:
    """Return DuckDB SQL sketch for regime features."""
    return f"""
    select
        'regime' as feature_set,
        '{version}' as version,
        symbol,
        asset_type,
        ts,
        timeframe,
        case when momentum > 0 then 1.0 when momentum < 0 then -1.0 else 0.0 end as trend_regime,
        case when rolling_volatility > long_volatility then 1.0 else 0.0 end as volatility_regime,
        case when rolling_liquidity < long_liquidity then 1.0 else 0.0 end as liquidity_regime,
        case when abs(rolling_correlation) > 0.6 then 1.0 else 0.0 end as correlation_regime,
        case when abs(momentum) / nullif(rolling_volatility, 0) > 1.0 then 1.0 else 0.0 end as multifractal_inefficiency_regime
    from input_regime_base
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


def _market_returns(groups: Mapping[tuple[str, str], Sequence[Mapping[str, object]]]) -> dict[tuple[str, str], float]:
    by_ts: dict[tuple[str, str], list[float]] = {}
    for group_rows in groups.values():
        returns = _simple_returns([float_or_none(row.get("close")) for row in group_rows])
        for row, value in zip(group_rows, returns, strict=False):
            if value is not None:
                key = (str(row.get("timeframe")), str(row.get("ts")))
                by_ts.setdefault(key, []).append(value)
    return {key: sum(values) / len(values) for key, values in by_ts.items() if values}


def _momentum(closes: Sequence[float | None], index: int, lag: int) -> float | None:
    close = closes[index]
    lag_close = closes[index - lag] if index >= lag else None
    if close is None or lag_close in (None, 0):
        return None
    return close / lag_close - 1.0


def _correlation(left: Sequence[float | None], right: Sequence[float | None], index: int, window: int) -> float | None:
    pairs = []
    start = max(0, index - window + 1)
    for left_value, right_value in zip(left[start : index + 1], right[start : index + 1], strict=False):
        if left_value is not None and right_value is not None:
            pairs.append((left_value, right_value))
    if len(pairs) < 2:
        return None
    left_mean = sum(pair[0] for pair in pairs) / len(pairs)
    right_mean = sum(pair[1] for pair in pairs) / len(pairs)
    covariance = sum((a - left_mean) * (b - right_mean) for a, b in pairs)
    left_var = sum((a - left_mean) ** 2 for a, _ in pairs)
    right_var = sum((b - right_mean) ** 2 for _, b in pairs)
    denominator = (left_var * right_var) ** 0.5
    return covariance / denominator if denominator else None


def _sign(value: float | None) -> float:
    if value is None:
        return 0.0
    if value > 0:
        return 1.0
    if value < 0:
        return -1.0
    return 0.0
