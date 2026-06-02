"""Graph change-point helpers for Quant4 topology experiments."""

from __future__ import annotations

from collections.abc import Sequence


def density_change_points(
    densities: Sequence[float],
    threshold: float,
) -> list[int]:
    """Return indices where graph density shifts by a threshold.

    Example:
        `density_change_points([0.1, 0.5], 0.2)`
    """
    points: list[int] = []
    for index in range(1, len(densities)):
        if abs(float(densities[index]) - float(densities[index - 1])) >= threshold:
            points.append(index)
    return points


def edge_turnover(
    previous_edges: Sequence[tuple[str, str]],
    next_edges: Sequence[tuple[str, str]],
) -> float:
    """Return Jaccard edge turnover between two graph windows.

    Example:
        `edge_turnover([("A", "B")], [("A", "C")])`
    """
    previous = {tuple(edge) for edge in previous_edges}
    current = {tuple(edge) for edge in next_edges}
    union = previous | current
    return 0.0 if not union else 1.0 - len(previous & current) / len(union)
