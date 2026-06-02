"""Graph path tracing for source intelligence explanations."""

from __future__ import annotations

import networkx as nx

from monitoring.models import DocumentTopic


def trace_graph_path(graph: nx.Graph, source_node: str, target_node: str) -> list[str]:
    """Return a shortest source/provider/event/entity path.

    Example:
        `path = trace_graph_path(graph, "source:1", "event:2")`
    """
    if not graph.has_node(source_node) or not graph.has_node(target_node):
        return []
    try:
        return [str(node) for node in nx.shortest_path(graph, source_node, target_node)]
    except nx.NetworkXNoPath:
        return []


def graph_trace_for_event(event_id: int) -> list[dict[str, object]]:
    """Return compact source-provider-event graph edges for an event.

    Example:
        `edges = graph_trace_for_event(12)`
    """
    topics = DocumentTopic.objects.filter(cluster_id=event_id).select_related(
        "document",
        "document__source",
    )
    return [_edge_from_topic(event_id, topic) for topic in topics[:50]]


def _edge_from_topic(event_id: int, topic: DocumentTopic) -> dict[str, object]:
    document = topic.document
    provider = (document.metadata or {}).get("provider") or document.source.name
    return {
        "event": f"event:{event_id}",
        "source": f"source:{document.source_id}",
        "provider": f"provider:{provider}",
        "article": f"article:{document.id}",
        "role": topic.role,
    }
