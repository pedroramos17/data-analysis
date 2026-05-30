"""Feature extraction from financial relation graphs."""

from __future__ import annotations

from collections.abc import Mapping

import networkx as nx

RATES_RELATIONS = frozenset({"lender_borrower", "rates_exposure"})
COMMODITY_RELATIONS = frozenset({"commodity_exposure", "futures_underlying"})
SECTOR_RELATIONS = frozenset({"same_sector", "same_industry", "competitor"})


def graph_feature_rows(
    graph: nx.DiGraph,
    seed_scores: Mapping[str, float] | None = None,
) -> dict[str, dict[str, float]]:
    """Return centrality, degree, and exposure features by symbol.

    Example:
        `rows = graph_feature_rows(graph, {"BANK": 1.0})`
    """
    pagerank = _safe_pagerank(graph)
    exposures = _relation_exposures(graph, seed_scores or {})
    return {
        str(node): _node_row(graph, str(node), pagerank, exposures)
        for node in graph.nodes
    }


def _safe_pagerank(graph: nx.DiGraph) -> dict[str, float]:
    nodes = [str(node) for node in graph.nodes]
    if not nodes:
        return {}
    scores = {node: 1.0 / len(nodes) for node in nodes}
    for _step in range(20):
        scores = _pagerank_step(graph, nodes, scores)
    return scores


def _pagerank_step(
    graph: nx.DiGraph,
    nodes: list[str],
    scores: Mapping[str, float],
) -> dict[str, float]:
    damping = 0.85
    next_scores = {node: (1.0 - damping) / len(nodes) for node in nodes}
    for source in nodes:
        _distribute_score(graph, source, scores, next_scores, damping)
    return next_scores


def _distribute_score(
    graph: nx.DiGraph,
    source: str,
    scores: Mapping[str, float],
    next_scores: dict[str, float],
    damping: float,
) -> None:
    outgoing = list(graph.out_edges(source, data=True))
    total_weight = sum(_edge_weight(data) for _s, _t, data in outgoing) or 1.0
    for _source, target, data in outgoing:
        share = _edge_weight(data) / total_weight
        next_scores[str(target)] += damping * scores[source] * share


def _node_row(
    graph: nx.DiGraph,
    node: str,
    pagerank: Mapping[str, float],
    exposures: Mapping[str, dict[str, float]],
) -> dict[str, float]:
    return {
        "pagerank": float(pagerank.get(node, 0.0)),
        "in_degree": float(graph.in_degree(node)),
        "out_degree": float(graph.out_degree(node)),
        "weighted_degree": _weighted_degree(graph, node),
        "rates_exposure": exposures.get(node, {}).get("rates_exposure", 0.0),
        "commodity_exposure": exposures.get(node, {}).get("commodity_exposure", 0.0),
        "sector_contagion": exposures.get(node, {}).get("sector_contagion", 0.0),
    }


def _weighted_degree(graph: nx.DiGraph, node: str) -> float:
    incoming = sum(
        _edge_weight(data) for _source, _target, data in graph.in_edges(node, data=True)
    )
    outgoing = sum(
        _edge_weight(data)
        for _source, _target, data in graph.out_edges(node, data=True)
    )
    return incoming + outgoing


def _relation_exposures(
    graph: nx.DiGraph,
    seed_scores: Mapping[str, float],
) -> dict[str, dict[str, float]]:
    exposures: dict[str, dict[str, float]] = {}
    for source, target, data in graph.edges(data=True):
        _add_exposure(exposures, str(target), data, seed_scores.get(str(source), 0.0))
    return exposures


def _add_exposure(
    exposures: dict[str, dict[str, float]],
    target: str,
    data: Mapping[str, object],
    score: float,
) -> None:
    relation_type = str(data.get("relation_type", ""))
    bucket = _exposure_bucket(relation_type)
    value = score * _edge_weight(data)
    exposures.setdefault(target, {})[bucket] = (
        exposures.setdefault(target, {}).get(bucket, 0.0) + value
    )


def _exposure_bucket(relation_type: str) -> str:
    if relation_type in RATES_RELATIONS:
        return "rates_exposure"
    if relation_type in COMMODITY_RELATIONS:
        return "commodity_exposure"
    if relation_type in SECTOR_RELATIONS:
        return "sector_contagion"
    return "sector_contagion"


def _edge_weight(data: Mapping[str, object]) -> float:
    return float(data.get("weight", 1.0)) * float(data.get("confidence", 1.0))
