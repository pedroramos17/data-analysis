"""Leakage-safe change-point baselines for multifractal feature streams."""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass
from statistics import mean, pstdev


@dataclass(frozen=True, slots=True)
class ChangePoint:
    """One past-window change-point diagnostic.

    Example:
        `point = ChangePoint(index=10, score=2.1, direction="up")`
    """

    index: int
    score: float
    direction: str

    def to_json_dict(self) -> dict[str, float | int | str]:
        """Return a JSON-safe change-point payload."""
        return {"index": self.index, "score": self.score, "direction": self.direction}


def detect_cusum_shifts(
    values: Sequence[float],
    window_size: int = 16,
    threshold: float = 2.0,
) -> list[ChangePoint]:
    """Detect level shifts using adjacent historical windows only.

    Example:
        `points = detect_cusum_shifts([0.1, 0.2, 0.8], window_size=2)`
    """
    _positive_int(window_size, "window_size")
    series = _finite_values(values)
    points: list[ChangePoint] = []
    for index in range(window_size * 2 - 1, len(series)):
        point = _candidate_shift(series, index, window_size, threshold)
        if point is not None:
            points.append(point)
    return points


def detect_rolling_zscore_shifts(
    values: Sequence[float],
    window_size: int = 16,
    threshold: float = 2.5,
) -> list[ChangePoint]:
    """Detect outlying current values relative to past observations.

    Example:
        `points = detect_rolling_zscore_shifts([0.1, 0.1, 1.0], 2)`
    """
    _positive_int(window_size, "window_size")
    series = _finite_values(values)
    points: list[ChangePoint] = []
    for index in range(window_size, len(series)):
        point = _zscore_shift(series, index, window_size, threshold)
        if point is not None:
            points.append(point)
    return points


def _candidate_shift(
    values: Sequence[float],
    index: int,
    window_size: int,
    threshold: float,
) -> ChangePoint | None:
    previous = values[index - (window_size * 2) + 1 : index - window_size + 1]
    current = values[index - window_size + 1 : index + 1]
    score = _standardized_gap(current, previous)
    if abs(score) < threshold:
        return None
    return ChangePoint(index=index, score=score, direction=_direction(score))


def _zscore_shift(
    values: Sequence[float],
    index: int,
    window_size: int,
    threshold: float,
) -> ChangePoint | None:
    sample = values[index - window_size : index]
    deviation = _safe_std(sample)
    score = (values[index] - mean(sample)) / deviation
    if abs(score) < threshold:
        return None
    return ChangePoint(index=index, score=score, direction=_direction(score))


def _standardized_gap(current: Sequence[float], previous: Sequence[float]) -> float:
    denominator = _safe_std(list(current) + list(previous))
    return (mean(current) - mean(previous)) / denominator


def _safe_std(values: Sequence[float]) -> float:
    if len(values) < 2:
        return 1.0
    deviation = pstdev(values)
    return deviation if deviation > 1e-12 else 1.0


def _direction(score: float) -> str:
    return "up" if score >= 0.0 else "down"


def _finite_values(values: Sequence[float]) -> list[float]:
    series = [float(value) for value in values]
    for value in series:
        if math.isfinite(value):
            continue
        raise ValueError(f"Invalid value {value!r}; expected finite float")
    return series


def _positive_int(value: int, label: str) -> None:
    if isinstance(value, int) and value > 0:
        return
    raise ValueError(f"Invalid {label} {value!r}; expected positive integer")
