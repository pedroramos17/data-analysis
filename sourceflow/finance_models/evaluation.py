"""Evaluation metrics for finance model outputs."""

from __future__ import annotations


def mean_squared_error(actual: list[float], predicted: list[float]) -> float:
    """Return mean squared error.

    Example:
        `mean_squared_error([1], [1]) == 0`
    """
    errors = [
        (left - right) ** 2 for left, right in zip(actual, predicted, strict=False)
    ]
    return sum(errors) / max(len(errors), 1)


def information_coefficient(actual: list[float], predicted: list[float]) -> float:
    """Return a Pearson-style information coefficient.

    Example:
        `information_coefficient([1, 2], [1, 2])`
    """
    if len(actual) < 2:
        return 0.0
    return _corr(actual, predicted)


def _corr(left: list[float], right: list[float]) -> float:
    mean_left = sum(left) / len(left)
    mean_right = sum(right) / len(right)
    numerator = sum(
        (a - mean_left) * (b - mean_right) for a, b in zip(left, right, strict=False)
    )
    denominator = _scale(left, mean_left) * _scale(right, mean_right)
    return numerator / denominator if denominator else 0.0


def _scale(values: list[float], mean_value: float) -> float:
    return sum((value - mean_value) ** 2 for value in values) ** 0.5
