"""Scaling helpers for multifractal preprocessing features."""

from __future__ import annotations

from collections.abc import Sequence

from quant.services.multifractal.preprocessing._series import (
    _coerce_finite_series,
    _mean,
    _percentile,
    _population_std,
)


def standardize_values(values: Sequence[float]) -> list[float]:
    """Return z-scored values using population standard deviation.

    Example:
        `scaled = standardize_values([1.0, 2.0, 3.0])`
    """
    validated = _coerce_finite_series(values, "values")
    scale = _population_std(validated)
    if scale == 0.0:
        return [0.0 for _value in validated]
    return [(value - _mean(validated)) / scale for value in validated]


def min_max_scale_values(
    values: Sequence[float],
    lower: float = 0.0,
    upper: float = 1.0,
) -> list[float]:
    """Scale values into a target interval.

    Example:
        `scaled = min_max_scale_values([1.0, 2.0], 0.0, 1.0)`
    """
    _validate_scale_bounds(lower, upper)
    validated = _coerce_finite_series(values, "values")
    value_min = min(validated)
    value_max = max(validated)
    if value_min == value_max:
        return [lower for _value in validated]
    return [
        _scale_value(value, value_min, value_max, lower, upper)
        for value in validated
    ]


def robust_scale_values(values: Sequence[float]) -> list[float]:
    """Scale values by median and interquartile range.

    Example:
        `scaled = robust_scale_values([1.0, 2.0, 100.0])`
    """
    validated = _coerce_finite_series(values, "values")
    median = _percentile(validated, 0.5)
    iqr = _percentile(validated, 0.75) - _percentile(validated, 0.25)
    if iqr == 0.0:
        return [0.0 for _value in validated]
    return [(value - median) / iqr for value in validated]


def _scale_value(
    value: float,
    value_min: float,
    value_max: float,
    lower: float,
    upper: float,
) -> float:
    ratio = (value - value_min) / (value_max - value_min)
    return lower + ratio * (upper - lower)


def _validate_scale_bounds(lower: float, upper: float) -> None:
    if upper > lower:
        return
    raise ValueError(f"Invalid scale bounds {(lower, upper)!r}; expected upper > lower")
