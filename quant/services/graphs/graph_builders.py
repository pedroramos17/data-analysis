"""Leakage-safe graph builders for Quant topology research."""

from __future__ import annotations

import math
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import date
from statistics import mean

from quant.services.graphs.hypergraphs import HypergraphBuilder
from sourceflow.config.feature_flags import require_feature

GraphSeries = Mapping[str, Sequence[tuple[date, float]]]
GraphEdge = dict[str, object]

__all__ = [
    "CorrelationGraphBuilder",
    "DynamicSparseGraphBuilder",
    "GraphBuildResult",
    "HypergraphBuilder",
    "IMFCoherenceGraphBuilder",
    "LeadLagSignatureGraphBuilder",
    "MutualInformationGraphBuilder",
    "NewsKnowledgeGraphBuilder",
    "PartialCorrelationGraphBuilder",
    "TDAComplexityGraphBuilder",
]


@dataclass(frozen=True, slots=True)
class GraphBuildResult:
    """Portable graph payload for persistence and downstream modules.

    Example:
        `GraphBuildResult(["AAA"], [], {}, {"builder": "stub"})`
    """

    nodes: list[str]
    edges: list[GraphEdge]
    adjacency: dict[str, dict[str, float]]
    metadata: dict[str, object] = field(default_factory=dict)


class CorrelationGraphBuilder:
    """Build pairwise correlation graphs from a past-only window."""

    def __init__(self, min_abs_weight: float = 0.0) -> None:
        self.min_abs_weight = min_abs_weight

    def build(self, series: GraphSeries, window_end: date) -> GraphBuildResult:
        """Build weighted edges using data at or before `window_end`."""
        window = _windowed_series(series, window_end)
        edges = _pairwise_edges(window, "correlation", _correlation)
        return _result("correlation", window, edges, self.min_abs_weight, window_end)


class PartialCorrelationGraphBuilder(CorrelationGraphBuilder):
    """Build a diagonal-shrunk partial-correlation proxy graph."""

    def build(self, series: GraphSeries, window_end: date) -> GraphBuildResult:
        """Build partial-correlation proxy edges from past-only data."""
        window = _windowed_series(series, window_end)
        edges = _pairwise_edges(window, "partial_correlation_proxy", _partial_proxy)
        return _result(
            "partial_correlation", window, edges, self.min_abs_weight, window_end
        )


class MutualInformationGraphBuilder(CorrelationGraphBuilder):
    """Build a dependency-free mutual-information fallback graph."""

    def build(self, series: GraphSeries, window_end: date) -> GraphBuildResult:
        """Build MI proxy edges from absolute correlation."""
        window = _windowed_series(series, window_end)
        edges = _pairwise_edges(window, "mutual_information_fallback", _mi_proxy)
        return _result(
            "mutual_information", window, edges, self.min_abs_weight, window_end
        )


class LeadLagSignatureGraphBuilder(CorrelationGraphBuilder):
    """Build a lead-lag signature proxy graph."""

    def build(self, series: GraphSeries, window_end: date) -> GraphBuildResult:
        """Build lead-lag edges using shifted past windows."""
        window = _windowed_series(series, window_end)
        edges = _pairwise_edges(window, "lead_lag_signature", _lead_lag_score)
        return _result(
            "lead_lag_signature", window, edges, self.min_abs_weight, window_end
        )


class IMFCoherenceGraphBuilder(CorrelationGraphBuilder):
    """Build an IMF-coherence fallback graph without EMD dependencies."""

    def build(self, series: GraphSeries, window_end: date) -> GraphBuildResult:
        """Build coherence proxy edges from demeaned past series."""
        window = _windowed_series(series, window_end)
        edges = _pairwise_edges(window, "imf_coherence_fallback", _coherence_score)
        return _result("imf_coherence", window, edges, self.min_abs_weight, window_end)


class TDAComplexityGraphBuilder(CorrelationGraphBuilder):
    """Build a lightweight topology-complexity graph."""

    def build(self, series: GraphSeries, window_end: date) -> GraphBuildResult:
        """Connect nodes with similar histogram complexity."""
        window = _windowed_series(series, window_end)
        edges = _pairwise_edges(window, "tda_complexity_fallback", _tda_similarity)
        return _result("tda_complexity", window, edges, self.min_abs_weight, window_end)


class DynamicSparseGraphBuilder(CorrelationGraphBuilder):
    """Build a sparse correlation graph stub for dynamic graph experiments."""

    def build(self, series: GraphSeries, window_end: date) -> GraphBuildResult:
        """Build a sparse graph from strongest past-only edges."""
        dense = CorrelationGraphBuilder(self.min_abs_weight).build(series, window_end)
        edge_limit = max(0, len(dense.nodes) - 1)
        edges = sorted(dense.edges, key=_abs_edge_weight, reverse=True)[:edge_limit]
        metadata = dict(dense.metadata) | {"builder": "dynamic_sparse_stub"}
        return GraphBuildResult(
            dense.nodes, edges, _adjacency(dense.nodes, edges), metadata
        )


class NewsKnowledgeGraphBuilder:
    """Adapt Sourceflow market knowledge graphs behind a feature flag."""

    def build(
        self,
        instruments: Sequence[object],
        relations: Sequence[object],
    ) -> GraphBuildResult:
        """Build a Sourceflow-backed knowledge graph when enabled."""
        require_feature("QUANT_SOURCEFLOW_KNOWLEDGE_GRAPH")
        from sourceflow.intelligence.market.knowledge_graph import build_company_graph

        graph = build_company_graph(instruments, relations)
        nodes = sorted(str(node) for node in graph.nodes)
        edges = [
            _sourceflow_edge(source, target, data)
            for source, target, data in graph.edges(data=True)
        ]
        return GraphBuildResult(
            nodes, edges, _adjacency(nodes, edges), _sourceflow_metadata()
        )


def _windowed_series(series: GraphSeries, window_end: date) -> dict[str, list[float]]:
    window: dict[str, list[float]] = {}
    for symbol, observations in series.items():
        past_values = [
            float(value) for stamp, value in observations if stamp <= window_end
        ]
        window[str(symbol)] = past_values
    return window


def _pairwise_edges(
    window: Mapping[str, Sequence[float]],
    relation_type: str,
    scorer: Callable[[Sequence[float], Sequence[float]], float],
) -> list[GraphEdge]:
    symbols = sorted(window)
    return [
        _edge(left, right, relation_type, scorer(window[left], window[right]))
        for index, left in enumerate(symbols)
        for right in symbols[index + 1 :]
    ]


def _result(
    builder: str,
    window: Mapping[str, Sequence[float]],
    edges: Sequence[GraphEdge],
    min_abs_weight: float,
    window_end: date,
) -> GraphBuildResult:
    nodes = sorted(window)
    filtered = [edge for edge in edges if abs(float(edge["weight"])) >= min_abs_weight]
    metadata = _metadata(builder, window, window_end)
    return GraphBuildResult(nodes, filtered, _adjacency(nodes, filtered), metadata)


def _metadata(
    builder: str,
    window: Mapping[str, Sequence[float]],
    window_end: date,
) -> dict[str, object]:
    counts = {symbol: len(values) for symbol, values in window.items()}
    return {
        "builder": builder,
        "max_observation_date": window_end.isoformat(),
        "used_observation_counts": counts,
    }


def _edge(
    source: str,
    target: str,
    relation_type: str,
    weight: float,
) -> GraphEdge:
    return {
        "source": source,
        "target": target,
        "weight": float(weight),
        "relation_type": relation_type,
    }


def _adjacency(
    nodes: Sequence[str],
    edges: Sequence[GraphEdge],
) -> dict[str, dict[str, float]]:
    adjacency = {node: {} for node in nodes}
    for edge in edges:
        source = str(edge["source"])
        target = str(edge["target"])
        adjacency[source][target] = float(edge["weight"])
        adjacency[target][source] = float(edge["weight"])
    return adjacency


def _correlation(left: Sequence[float], right: Sequence[float]) -> float:
    length = min(len(left), len(right))
    if length < 2:
        return 0.0
    left_sample = [float(value) for value in left[:length]]
    right_sample = [float(value) for value in right[:length]]
    return _safe_ratio(
        _covariance(left_sample, right_sample),
        _vol_product(left_sample, right_sample),
    )


def _covariance(left: Sequence[float], right: Sequence[float]) -> float:
    left_mean = mean(left)
    right_mean = mean(right)
    return mean(
        (left[i] - left_mean) * (right[i] - right_mean) for i in range(len(left))
    )


def _vol_product(left: Sequence[float], right: Sequence[float]) -> float:
    return math.sqrt(_covariance(left, left) * _covariance(right, right))


def _partial_proxy(left: Sequence[float], right: Sequence[float]) -> float:
    return 0.8 * _correlation(left, right)


def _mi_proxy(left: Sequence[float], right: Sequence[float]) -> float:
    correlation = max(-0.999999, min(0.999999, _correlation(left, right)))
    return -0.5 * math.log(max(1e-12, 1 - correlation * correlation))


def _lead_lag_score(left: Sequence[float], right: Sequence[float]) -> float:
    if len(left) < 3 or len(right) < 3:
        return 0.0
    return _correlation(left[:-1], right[1:]) - _correlation(right[:-1], left[1:])


def _coherence_score(left: Sequence[float], right: Sequence[float]) -> float:
    return abs(_correlation(_demean(left), _demean(right)))


def _tda_similarity(left: Sequence[float], right: Sequence[float]) -> float:
    return 1.0 / (1.0 + abs(_complexity(left) - _complexity(right)))


def _complexity(values: Sequence[float]) -> float:
    if len(values) < 2:
        return 0.0
    return sum(
        abs(float(values[index]) - float(values[index - 1]))
        for index in range(1, len(values))
    )


def _demean(values: Sequence[float]) -> list[float]:
    if not values:
        return []
    center = mean(float(value) for value in values)
    return [float(value) - center for value in values]


def _safe_ratio(numerator: float, denominator: float) -> float:
    return 0.0 if denominator == 0 else numerator / denominator


def _abs_edge_weight(edge: GraphEdge) -> float:
    return abs(float(edge["weight"]))


def _sourceflow_edge(
    source: object,
    target: object,
    data: Mapping[str, object],
) -> GraphEdge:
    return {
        "source": str(source),
        "target": str(target),
        "weight": float(data.get("weight", 1.0)),
        "relation_type": str(data.get("relation_type", "knowledge")),
    }


def _sourceflow_metadata() -> dict[str, object]:
    return {"builder": "sourceflow_news_knowledge", "claim_scope": "comparison_graph"}
