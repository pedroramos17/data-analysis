"""Recurrence helpers for topology experiments."""

from __future__ import annotations

from collections.abc import Sequence


def recurrence_matrix(
    values: Sequence[float],
    epsilon: float,
) -> list[list[int]]:
    """Return a binary recurrence matrix from local values.

    Example:
        `recurrence_matrix([1.0, 1.1], 0.2)`
    """
    return [
        [_recurs(left, right, epsilon) for right in values]
        for left in values
    ]


def recurrence_rate(values: Sequence[float], epsilon: float) -> float:
    """Return the recurrence rate for a value sequence.

    Example:
        `recurrence_rate([1.0, 1.1], 0.2)`
    """
    matrix = recurrence_matrix(values, epsilon)
    total = len(matrix) * len(matrix)
    return 0.0 if total == 0 else sum(map(sum, matrix)) / total


def _recurs(left: float, right: float, epsilon: float) -> int:
    return int(abs(float(left) - float(right)) <= epsilon)
