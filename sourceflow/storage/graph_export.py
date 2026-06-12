"""Optional RDF / Neo4j export for the SQL-backed knowledge graph.

The canonical graph lives in the ``KnowledgeEdge`` table (Phase 5). These helpers
are the optional adapters the storage rules call for: a dependency-free N-Triples
exporter (reproducible, ordered) and a Neo4j adapter that activates only when the
``neo4j`` driver is installed.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Iterable


class MissingGraphBackend(RuntimeError):
    """Raised when an optional graph backend (neo4j) is not installed."""


def _iri(node_type: str, node_id: Any) -> str:
    return f"<urn:sourceflow:{node_type}:{node_id}>"


def edge_to_triples(edge: Any) -> list[str]:
    """Return the N-Triples lines for one knowledge edge."""
    subject = _iri(edge.source_node_type, edge.source_node_id)
    predicate = f"<urn:sourceflow:edge:{edge.edge_type}>"
    obj = _iri(edge.target_node_type, edge.target_node_id)
    confidence = f"<urn:sourceflow:edge:{edge.edge_type}:confidence>"
    return [
        f"{subject} {predicate} {obj} .",
        f'{subject} {confidence} "{float(edge.confidence)}"^^<http://www.w3.org/2001/XMLSchema#decimal> .',
    ]


def to_ntriples(edges: Iterable[Any]) -> str:
    """Serialize edges to a deterministic N-Triples document."""
    lines: list[str] = []
    for edge in edges:
        lines.extend(edge_to_triples(edge))
    return "\n".join(lines) + ("\n" if lines else "")


def export_graph_ntriples(dest_path: str | Path) -> Path:
    """Export the whole knowledge graph to an N-Triples file (ordered by edge id)."""
    from sourceflow.models import KnowledgeEdge

    path = Path(dest_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(to_ntriples(KnowledgeEdge.objects.order_by("pk")), encoding="utf-8")
    return path


class Neo4jGraphAdapter:  # pragma: no cover - exercised only when neo4j is installed
    """Optional Neo4j adapter; requires the ``neo4j`` driver to be installed."""

    def __init__(self, uri: str, *, auth: tuple[str, str] | None = None) -> None:
        try:
            from neo4j import GraphDatabase
        except ImportError as exc:
            raise MissingGraphBackend(
                "neo4j driver is not installed; the SQL graph store remains the default backend"
            ) from exc
        self._driver = GraphDatabase.driver(uri, auth=auth)

    def upsert_edges(self, edges: Iterable[Any]) -> int:
        count = 0
        with self._driver.session() as session:
            for edge in edges:
                session.run(
                    "MERGE (s:Node {key:$s}) MERGE (t:Node {key:$t}) "
                    "MERGE (s)-[r:REL {type:$type}]->(t) SET r.confidence=$confidence",
                    s=f"{edge.source_node_type}:{edge.source_node_id}",
                    t=f"{edge.target_node_type}:{edge.target_node_id}",
                    type=edge.edge_type,
                    confidence=float(edge.confidence),
                )
                count += 1
        return count

    def close(self) -> None:
        self._driver.close()
