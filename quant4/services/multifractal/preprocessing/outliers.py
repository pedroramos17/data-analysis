"""Outlier flags and optional winsorization for robust preprocessing."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from quant4.services.multifractal.preprocessing._series import (
    _coerce_finite_series,
    _mean,
    _percentile,
    _population_std,
)


@dataclass(frozen=True, slots=True)
class OutlierFlag:
    """Diagnostic flag that preserves the original observation.

    Example:
        `flag = flag_zscore_outliers([1.0, 100.0], 1.0)[0]`
    """

    index: int
    value: float
    is_outlier: bool
    score: float
    reason: str


def flag_zscore_outliers(
    values: Sequence[float],
    z_threshold: float = 3.0,
) -> list[OutlierFlag]:
    """Flag z-score outliers without removing observations.

    Example:
        `flags = flag_zscore_outliers([1.0, 2.0, 100.0], 2.0)`
    """
    _validate_positive_threshold(z_threshold)
    validated = _coerce_finite_series(values, "values")
    scale = _population_std(validated)
    if scale == 0.0:
        return [
            _flag(index, value, 0.0, False)
            for index, value in enumerate(validated)
        ]
    return [
        _zscore_flag(index, value, validated, scale, z_threshold)
        for index, value in enumerate(validated)
    ]


def winsorize_values(
    values: Sequence[float],
    lower_quantile: float = 0.05,
    upper_quantile: float = 0.95,
) -> list[float]:
    """Cap extremes at quantile bounds while preserving row count.

    Example:
        `clean = winsorize_values([1.0, 2.0, 100.0], 0.0, 0.9)`
    """
    _validate_quantile_pair(lower_quantile, upper_quantile)
    validated = _coerce_finite_series(values, "values")
    lower = _percentile(validated, lower_quantile)
    upper = _percentile(validated, upper_quantile)
    return [min(max(value, lower), upper) for value in validated]


def _zscore_flag(
    index: int,
    value: float,
    values: Sequence[float],
    scale: float,
    z_threshold: float,
) -> OutlierFlag:
    score = abs((value - _mean(values)) / scale)
    return _flag(index, value, score, score > z_threshold)


def _flag(index: int, value: float, score: float, is_outlier: bool) -> OutlierFlag:
    reason = "zscore_threshold_exceeded" if is_outlier else "within_threshold"
    return OutlierFlag(index, value, is_outlier, score, reason)


def _validate_positive_threshold(value: float) -> None:
    if value > 0.0:
        return
    raise ValueError(f"Invalid z_threshold {value!r}; expected positive float")


def _validate_quantile_pair(lower: float, upper: float) -> None:
    if 0.0 <= lower <= upper <= 1.0:
        return
    raise ValueError(
        f"Invalid quantile pair {(lower, upper)!r}; "
        "expected 0 <= lower <= upper <= 1"
    )
