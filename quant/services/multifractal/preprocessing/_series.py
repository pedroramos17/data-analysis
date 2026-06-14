"""Internal numeric helpers for multifractal preprocessing."""

from __future__ import annotations

import math
from collections.abc import Sequence


def _coerce_finite_series(values: Sequence[float], label: str) -> list[float]:
    if not values:
        raise ValueError(
            f"Invalid {label} {values!r}; expected non-empty numeric series"
        )
    coerced = [_finite_float(value, label) for value in values]
    return coerced


def _coerce_positive_series(values: Sequence[float], label: str) -> list[float]:
    coerced = _coerce_finite_series(values, label)
    for value in coerced:
        _positive_float(value, label)
    return coerced


def _finite_float(value: object, label: str) -> float:
    try:
        parsed = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(
            f"Invalid {label} value {value!r}; expected finite float"
        ) from exc
    if math.isfinite(parsed):
        return parsed
    raise ValueError(f"Invalid {label} value {value!r}; expected finite float")


def _positive_float(value: float, label: str) -> float:
    if value > 0.0:
        return value
    raise ValueError(f"Invalid {label} value {value!r}; expected positive float")


def _positive_int(value: int, label: str) -> int:
    if isinstance(value, int) and value > 0:
        return value
    raise ValueError(f"Invalid {label} {value!r}; expected positive integer")


def _mean(values: Sequence[float]) -> float:
    return sum(values) / len(values)


def _population_std(values: Sequence[float]) -> float:
    center = _mean(values)
    return math.sqrt(sum((value - center) ** 2 for value in values) / len(values))


def _percentile(values: Sequence[float], quantile: float) -> float:
    _validate_quantile(quantile, "quantile")
    ordered = sorted(values)
    position = quantile * (len(ordered) - 1)
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return ordered[lower]
    return _interpolate(ordered[lower], ordered[upper], position - lower)


def _validate_quantile(value: float, label: str) -> None:
    if 0.0 <= value <= 1.0:
        return
    raise ValueError(f"Invalid {label} {value!r}; expected float in [0.0, 1.0]")


def _interpolate(left: float, right: float, weight: float) -> float:
    return left + (right - left) * weight
