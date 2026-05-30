"""Build financial relation graphs."""

from __future__ import annotations

from collections.abc import Iterable, Mapping

import networkx as nx

from sourceflow.config.feature_flags import require_feature


def build_financial_graph(
    instruments: Iterable[str],
    relations: Iterable[Mapping[str, object]],
) -> nx.DiGraph:
    """Build a directed graph from instruments and typed relations.

    Example:
        `graph = build_financial_graph(["AAPL"], [])`
    """
    require_feature("FIN_GRAPH_CORE")
    graph = nx.DiGraph()
    for symbol in instruments:
        graph.add_node(str(symbol))
    for relation in relations:
        _add_relation(graph, relation)
    return graph


def _add_relation(graph: nx.DiGraph, relation: Mapping[str, object]) -> None:
    source = str(relation.get("source", relation.get("source_instrument", "")))
    target = str(relation.get("target", relation.get("target_instrument", "")))
    if not source or not target:
        raise ValueError(f"Invalid relation {relation!r}; expected source and target")
    graph.add_edge(source, target, **_edge_attributes(relation))


def _edge_attributes(relation: Mapping[str, object]) -> dict[str, object]:
    return {
        "relation_type": str(relation.get("relation_type", "")),
        "weight": float(relation.get("weight", 1.0)),
        "confidence": float(relation.get("confidence", 1.0)),
        "evidence_type": str(relation.get("evidence_type", "")),
        "evidence_url": str(relation.get("evidence_url", "")),
    }
