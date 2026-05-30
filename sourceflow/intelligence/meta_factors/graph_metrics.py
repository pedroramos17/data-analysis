"""NetworkX graph metrics for source/provider/event/entity paths."""

from __future__ import annotations

import networkx as nx

from sourceflow.intelligence.meta_factors.articles import article_event_rows
from sourceflow.intelligence.meta_factors.common import MetaFactorContext
from sourceflow.intelligence.meta_factors.entities import entity_event_rows


def build_source_event_graph(context: MetaFactorContext) -> nx.Graph:
    """Build an MVP source-event-entity graph.

    Example:
        `graph = build_source_event_graph(context)`
    """
    graph = nx.Graph()
    for row in article_event_rows(context):
        graph.add_edge(f"source:{row['source_id']}", f"event:{row['event_id']}")
        graph.add_edge(f"provider:{row['provider']}", f"event:{row['event_id']}")
    for row in entity_event_rows(context):
        graph.add_edge(f"entity:{row['entity']}", f"event:{row['event_id']}")
    return graph


def graph_metric_rows(context: MetaFactorContext) -> list[dict[str, object]]:
    """Return graph spread metrics by event.

    Example:
        `rows = graph_metric_rows(context)`
    """
    graph = build_source_event_graph(context)
    return [
        _event_graph_row(graph, node)
        for node in graph.nodes
        if str(node).startswith("event:")
    ]


def _event_graph_row(graph: nx.Graph, node: object) -> dict[str, object]:
    event_id = int(str(node).split(":", 1)[1])
    return {
        "event_id": event_id,
        "graph_degree": float(graph.degree(node)),
        "graph_component_size": float(len(nx.node_connected_component(graph, node))),
    }
