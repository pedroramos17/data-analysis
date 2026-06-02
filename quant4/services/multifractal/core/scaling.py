"""Scaling-range selection and regression for Quant4 MF-DFA."""

from __future__ import annotations

import math
from collections.abc import Sequence

from quant4.services.multifractal.core.types import ScalingDiagnostics


def default_scale_grid(
    length: int,
    min_scale: int | None = None,
    max_scale: int | None = None,
    preferred_count: int = 12,
    detrending_order: int = 1,
    min_segments_per_scale: int = 4,
) -> tuple[int, ...]:
    """Return conservative log-spaced integer scales for MF-DFA.

    Example:
        `scales = default_scale_grid(512, preferred_count=8)`
    """
    _validate_positive_int(length, "length")
    _validate_positive_int(preferred_count, "preferred_count")
    lower = min_scale or max(8, detrending_order + 3)
    upper = max_scale or max(lower, length // min_segments_per_scale)
    _validate_scale_bounds(lower, upper, length)
    return _log_spaced_unique_ints(lower, upper, preferred_count)


def build_scaling_diagnostic(
    points: Sequence[tuple[int, float]],
    q: float,
    robust_regression: bool,
    min_scale: int | None,
    max_scale: int | None,
    min_scale_count: int,
) -> ScalingDiagnostics:
    """Fit log Fq(s) against log(s) and return diagnostics.

    Example:
        `diagnostic = build_scaling_diagnostic(points, 2.0, False, None, None, 3)`
    """
    filtered = _filter_scaling_points(points, min_scale, max_scale)
    _validate_scale_count(filtered, min_scale_count, q)
    log_points = [(math.log(scale), math.log(value)) for scale, value in filtered]
    slope, intercept = _fit_regression(log_points, robust_regression)
    r_squared = _r_squared(log_points, slope, intercept)
    warnings = _diagnostic_warnings(filtered, r_squared, min_scale_count)
    return ScalingDiagnostics(
        q,
        slope,
        intercept,
        r_squared,
        len(filtered),
        (filtered[0][0], filtered[-1][0]),
        tuple(scale for scale, _value in filtered),
        warnings,
    )


def _log_spaced_unique_ints(lower: int, upper: int, count: int) -> tuple[int, ...]:
    if lower == upper:
        return (lower,)
    values: list[int] = []
    for index in range(count):
        ratio = index / (count - 1)
        scale = round(math.exp(math.log(lower) + ratio * math.log(upper / lower)))
        values.append(max(lower, min(upper, scale)))
    return tuple(sorted(set(values)))


def _filter_scaling_points(
    points: Sequence[tuple[int, float]],
    min_scale: int | None,
    max_scale: int | None,
) -> list[tuple[int, float]]:
    filtered = [
        (scale, value)
        for scale, value in points
        if _is_valid_scaling_point(scale, value, min_scale, max_scale)
    ]
    return sorted(filtered, key=lambda point: point[0])


def _is_valid_scaling_point(
    scale: int,
    value: float,
    min_scale: int | None,
    max_scale: int | None,
) -> bool:
    if scale <= 0 or value <= 0.0:
        return False
    if not math.isfinite(value):
        return False
    if min_scale is not None and scale < min_scale:
        return False
    return max_scale is None or scale <= max_scale


def _fit_regression(
    log_points: Sequence[tuple[float, float]],
    robust_regression: bool,
) -> tuple[float, float]:
    if robust_regression:
        return _theil_sen_fit(log_points)
    return _ordinary_least_squares(log_points)


def _ordinary_least_squares(
    points: Sequence[tuple[float, float]],
) -> tuple[float, float]:
    mean_x = sum(x for x, _y in points) / len(points)
    mean_y = sum(y for _x, y in points) / len(points)
    denominator = sum((x - mean_x) ** 2 for x, _y in points)
    if denominator == 0.0:
        raise ValueError(f"Invalid scaling points {points!r}; expected unique scales")
    slope = sum((x - mean_x) * (y - mean_y) for x, y in points) / denominator
    return slope, mean_y - slope * mean_x


def _theil_sen_fit(points: Sequence[tuple[float, float]]) -> tuple[float, float]:
    slopes = [
        (right_y - left_y) / (right_x - left_x)
        for left_index, (left_x, left_y) in enumerate(points)
        for right_x, right_y in points[left_index + 1 :]
        if right_x != left_x
    ]
    slope = _median(slopes)
    intercept = _median([y - slope * x for x, y in points])
    return slope, intercept


def _r_squared(
    points: Sequence[tuple[float, float]],
    slope: float,
    intercept: float,
) -> float:
    mean_y = sum(y for _x, y in points) / len(points)
    total = sum((y - mean_y) ** 2 for _x, y in points)
    residual = sum((y - (slope * x + intercept)) ** 2 for x, y in points)
    if total == 0.0:
        return 1.0 if residual == 0.0 else 0.0
    return max(0.0, min(1.0, 1.0 - residual / total))


def _diagnostic_warnings(
    points: Sequence[tuple[int, float]],
    r_squared: float,
    min_scale_count: int,
) -> tuple[str, ...]:
    warnings: list[str] = []
    if len(points) <= min_scale_count:
        warnings.append("minimal_scale_count")
    if r_squared < 0.8:
        warnings.append("low_scaling_r_squared")
    return tuple(warnings)


def _validate_scale_count(
    points: Sequence[tuple[int, float]],
    min_scale_count: int,
    q: float,
) -> None:
    if len(points) >= min_scale_count and len(points) >= 2:
        return
    raise ValueError(
        f"Invalid scaling points for q={q!r}; "
        f"expected at least {max(2, min_scale_count)} positive scales"
    )


def _validate_scale_bounds(lower: int, upper: int, length: int) -> None:
    if 1 <= lower <= upper < length:
        return
    raise ValueError(
        f"Invalid scale bounds {(lower, upper, length)!r}; "
        "expected 1 <= min_scale <= max_scale < series length"
    )


def _validate_positive_int(value: int, label: str) -> None:
    if isinstance(value, int) and value > 0:
        return
    raise ValueError(f"Invalid {label} {value!r}; expected positive integer")


def _median(values: Sequence[float]) -> float:
    ordered = sorted(values)
    middle = len(ordered) // 2
    if len(ordered) % 2 == 1:
        return ordered[middle]
    return (ordered[middle - 1] + ordered[middle]) / 2.0
