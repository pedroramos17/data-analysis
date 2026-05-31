"""VaR and expected shortfall helpers for multifractal risk reports."""

from __future__ import annotations

import math
from collections.abc import Sequence


def historical_var(returns: Sequence[float], confidence_level: float = 0.95) -> float:
    """Return historical loss VaR as a positive number.

    Example:
        `value = historical_var([-0.01, 0.02], 0.95)`
    """
    values = _losses(returns)
    _confidence(confidence_level)
    return _percentile(values, confidence_level)


def expected_shortfall(
    returns: Sequence[float],
    confidence_level: float = 0.95,
) -> float:
    """Return historical expected shortfall beyond VaR.

    Example:
        `value = expected_shortfall([-0.01, -0.05, 0.02], 0.95)`
    """
    losses = _losses(returns)
    threshold = historical_var(returns, confidence_level)
    tail = [loss for loss in losses if loss >= threshold]
    return sum(tail) / len(tail) if tail else threshold


def ewma_var(
    returns: Sequence[float],
    confidence_level: float = 0.95,
    decay: float = 0.94,
) -> float:
    """Return EWMA normal-approximation VaR.

    Example:
        `value = ewma_var(returns, 0.95)`
    """
    values = _finite_returns(returns)
    _confidence(confidence_level)
    _decay(decay)
    variance = _ewma_variance(values, decay)
    return _normal_z(confidence_level) * math.sqrt(variance)


def kupiec_hit_rate(returns: Sequence[float], var_level: float) -> dict[str, float]:
    """Return a simple VaR breach hit-rate report.

    Example:
        `report = kupiec_hit_rate(returns, 0.02)`
    """
    _positive_float(var_level, "var_level")
    losses = _losses(returns)
    breaches = sum(1 for loss in losses if loss > var_level)
    return {"breaches": float(breaches), "hit_rate": breaches / len(losses)}


def _ewma_variance(values: Sequence[float], decay: float) -> float:
    variance = values[0] * values[0]
    for value in values[1:]:
        variance = decay * variance + (1.0 - decay) * value * value
    return variance


def _losses(returns: Sequence[float]) -> list[float]:
    return [-value for value in _finite_returns(returns)]


def _finite_returns(returns: Sequence[float]) -> list[float]:
    if not returns:
        raise ValueError(f"Invalid returns {returns!r}; expected non-empty series")
    values = [float(value) for value in returns]
    for value in values:
        if math.isfinite(value):
            continue
        raise ValueError(f"Invalid return value {value!r}; expected finite float")
    return values


def _percentile(values: Sequence[float], quantile: float) -> float:
    ordered = sorted(values)
    position = quantile * (len(ordered) - 1)
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return ordered[lower]
    return ordered[lower] + (ordered[upper] - ordered[lower]) * (position - lower)


def _normal_z(confidence_level: float) -> float:
    if confidence_level >= 0.99:
        return 2.326
    if confidence_level >= 0.975:
        return 1.96
    if confidence_level >= 0.95:
        return 1.645
    return 1.282


def _confidence(value: float) -> None:
    if 0.5 < value < 1.0:
        return
    raise ValueError(f"Invalid confidence_level {value!r}; expected float in (0.5, 1)")


def _decay(value: float) -> None:
    if 0.0 < value < 1.0:
        return
    raise ValueError(f"Invalid decay {value!r}; expected float in (0, 1)")


def _positive_float(value: float, label: str) -> None:
    if value > 0.0 and math.isfinite(value):
        return
    raise ValueError(f"Invalid {label} {value!r}; expected positive finite float")
