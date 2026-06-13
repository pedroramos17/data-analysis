"""Knowledge graph helpers for market factor propagation."""

from __future__ import annotations

from collections.abc import Iterable, Mapping

import networkx as nx

from sourceflow.finance_core.contracts import CompanyRelation, InstrumentRef


def build_company_graph(
    instruments: Iterable[InstrumentRef],
    relations: Iterable[CompanyRelation],
) -> nx.DiGraph:
    """Build a directed weighted company and instrument graph.

    Example:
        `graph = build_company_graph(instruments, relations)`
    """
    graph = nx.DiGraph()
    for instrument in instruments:
        graph.add_node(instrument.symbol, **_instrument_attrs(instrument))
    for relation in relations:
        graph.add_node(relation.source_symbol)
        graph.add_node(relation.target_symbol)
        graph.add_edge(
            relation.source_symbol, relation.target_symbol, **_edge_attrs(relation)
        )
    return graph


def relation_weight(
    graph: nx.DiGraph,
    source_symbol: str,
    target_symbol: str,
) -> float:
    """Return edge weight or zero when no relation exists.

    Example:
        `relation_weight(graph, "AAPL", "MSFT")`
    """
    if not graph.has_edge(source_symbol, target_symbol):
        return 0.0
    return float(graph[source_symbol][target_symbol].get("weight", 0.0))


def neighbor_symbols(
    graph: nx.DiGraph,
    symbol: str,
    relation_types: Iterable[str] | None = None,
    min_weight: float = 0.0,
) -> list[str]:
    """Return outgoing neighbors filtered by relation type and weight.

    Example:
        `neighbor_symbols(graph, "AAPL", {"supplier"}, 0.5)`
    """
    if symbol not in graph:
        return []
    relation_filter = set(relation_types or [])
    return [
        target
        for target in graph.successors(symbol)
        if _edge_matches(graph[symbol][target], relation_filter, min_weight)
    ]


def graph_exposure_scores(
    graph: nx.DiGraph,
    seed_scores: Mapping[str, float],
    decay: float = 0.85,
    steps: int = 3,
) -> dict[str, float]:
    """Propagate seed scores through weighted graph edges.

    Example:
        `scores = graph_exposure_scores(graph, {"BANK": 1.0})`
    """
    scores = {symbol: float(score) for symbol, score in seed_scores.items()}
    frontier = scores.copy()
    for _step in range(max(steps, 0)):
        frontier = _next_frontier(graph, frontier, decay)
        _merge_scores(scores, frontier)
    return scores


def _instrument_attrs(instrument: InstrumentRef) -> dict[str, object]:
    return {
        "exchange": instrument.exchange,
        "asset_class": instrument.asset_class,
        "currency": instrument.currency,
        "country": instrument.country,
        "sector": instrument.sector,
        "industry": instrument.industry,
    }


def _edge_attrs(relation: CompanyRelation) -> dict[str, object]:
    return {
        "relation_type": relation.relation_type,
        "weight": relation.weight,
        "evidence": relation.evidence,
        "source": relation.source,
    }


def _edge_matches(
    edge: Mapping[str, object],
    relation_filter: set[str],
    min_weight: float,
) -> bool:
    relation_type = str(edge.get("relation_type", ""))
    weight = float(edge.get("weight", 0.0))
    type_matches = not relation_filter or relation_type in relation_filter
    return type_matches and weight >= min_weight


def _next_frontier(
    graph: nx.DiGraph,
    frontier: Mapping[str, float],
    decay: float,
) -> dict[str, float]:
    next_scores: dict[str, float] = {}
    for source, score in frontier.items():
        for target in graph.successors(source) if source in graph else []:
            propagated = score * relation_weight(graph, source, target) * decay
            next_scores[target] = next_scores.get(target, 0.0) + propagated
    return next_scores


def _merge_scores(scores: dict[str, float], additions: Mapping[str, float]) -> None:
    for symbol, value in additions.items():
        scores[symbol] = scores.get(symbol, 0.0) + value
