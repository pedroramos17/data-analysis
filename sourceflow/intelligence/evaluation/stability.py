"""Score factor stability across windows or providers."""

from __future__ import annotations

from statistics import mean


def stability_score(rows: list[dict[str, object]], factor_name: str) -> float:
    """Return a bounded stability score from coefficient of variation.

    Example:
        `score = stability_score(rows, "coverage_intensity")`
    """
    values = [float(row.get(factor_name, 0) or 0) for row in rows]
    if not values:
        return 0.0
    average = abs(mean(values))
    variation = _std(values) / max(average, 1e-9)
    return max(0.0, min(1.0, 1 / (1 + variation)))


def _std(values: list[float]) -> float:
    if len(values) < 2:
        return 0.0
    average = mean(values)
    return (sum((value - average) ** 2 for value in values) / len(values)) ** 0.5
