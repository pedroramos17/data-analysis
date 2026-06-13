"""Lightweight topology metrics for Quant graph snapshots."""

from __future__ import annotations

from collections.abc import Sequence

from quant.services.graphs.graph_builders import GraphBuildResult


def graph_density(result: GraphBuildResult) -> float:
    """Return directed density for a graph payload.

    Example:
        `graph_density(result)`
    """
    possible_edges = len(result.nodes) * max(0, len(result.nodes) - 1)
    return 0.0 if possible_edges == 0 else len(result.edges) / possible_edges


def topology_complexity_score(result: GraphBuildResult) -> dict[str, object]:
    """Return dependency-free topology complexity metadata.

    Example:
        `topology_complexity_score(result)["method"]`
    """
    degrees = [len(result.adjacency.get(node, {})) for node in result.nodes]
    return {
        "method": "degree_entropy_fallback",
        "density": graph_density(result),
        "degree_entropy": _entropy(degrees),
    }


def _entropy(values: Sequence[int]) -> float:
    total = sum(values)
    if total == 0:
        return 0.0
    probabilities = [value / total for value in values if value]
    return -sum(probability * _log2(probability) for probability in probabilities)


def _log2(value: float) -> float:
    import math

    return math.log(value, 2)
