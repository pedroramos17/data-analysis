"""GraphStore protocol and SQL-backed knowledge graph implementation.

The SQL backend persists edges into the canonical ``KnowledgeEdge`` table and
treats canonical rows (sources, documents, chunks, entities, claims, events,
risk factors, assets, instruments, portfolios) as graph nodes referenced by
type and identifier. Every edge carries edge type, confidence, provenance, and
an observation timestamp; unknown edge types are rejected.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Protocol

from sourceflow.kg.schema import GraphNodeRef, GraphSchemaError, node_ref, validate_edge


@dataclass(frozen=True)
class Neighbor:
    """Neighbor node plus the edge that connects it."""

    node: GraphNodeRef
    edge: object


class GraphStore(Protocol):
    """Provider contract for persistent knowledge graph backends."""

    def add_node(self, node_type: str, node_id: object) -> GraphNodeRef:
        """Validate and return a canonical node reference."""

    def add_edge(
        self,
        source: GraphNodeRef,
        target: GraphNodeRef,
        edge_type: str,
        *,
        confidence: Decimal,
        provenance: dict[str, object],
        source_document: object | None = None,
        evidence_span: object | None = None,
        observed_at: datetime | None = None,
    ) -> object:
        """Upsert a validated, provenance-carrying edge."""

    def get_neighbors(
        self,
        node: GraphNodeRef,
        *,
        edge_type: str | None = None,
        direction: str = "out",
    ) -> list[Neighbor]:
        """Return neighbor nodes with their connecting edges."""

    def find_paths(
        self,
        start: GraphNodeRef,
        end: GraphNodeRef,
        *,
        max_depth: int = 3,
    ) -> list[list[object]]:
        """Return simple directed edge paths from start to end."""

    def query(
        self,
        *,
        edge_type: str | None = None,
        source: GraphNodeRef | None = None,
        target: GraphNodeRef | None = None,
        min_confidence: Decimal | None = None,
    ) -> list[object]:
        """Return edges matching the given filters."""

    def upsert_claim(self, claim: object) -> list[object]:
        """Map a canonical claim into graph nodes and edges."""

    def upsert_event(self, event: object) -> list[object]:
        """Map a canonical event into graph nodes and edges."""


class SqlGraphStore:
    """Local-first ``GraphStore`` backed by the ``KnowledgeEdge`` table."""

    provenance_creator = "sourceflow.kg.store.SqlGraphStore"

    def add_node(self, node_type: str, node_id: object) -> GraphNodeRef:
        return node_ref(node_type, node_id)

    def add_edge(
        self,
        source: GraphNodeRef,
        target: GraphNodeRef,
        edge_type: str,
        *,
        confidence: Decimal,
        provenance: dict[str, object],
        source_document: object | None = None,
        evidence_span: object | None = None,
        observed_at: datetime | None = None,
    ) -> object:
        from django.utils import timezone
        from sourceflow.models import KnowledgeEdge

        validate_edge(edge_type, source, target)
        if not provenance:
            raise GraphSchemaError("every edge must carry non-empty provenance")
        edge, created = KnowledgeEdge.objects.get_or_create(
            edge_type=edge_type,
            source_node_type=source.node_type,
            source_node_id=source.node_id,
            target_node_type=target.node_type,
            target_node_id=target.node_id,
            defaults={
                "confidence": confidence,
                "provenance_json": provenance,
                "source_document": source_document,
                "evidence_span": evidence_span,
                "observed_at": observed_at or timezone.now(),
            },
        )
        if not created:
            edge.confidence = confidence
            edge.provenance_json = provenance
            if source_document is not None:
                edge.source_document = source_document
            if evidence_span is not None:
                edge.evidence_span = evidence_span
            if observed_at is not None:
                edge.observed_at = observed_at
            edge.save(
                update_fields=[
                    "confidence",
                    "provenance_json",
                    "source_document",
                    "evidence_span",
                    "observed_at",
                    "updated_at",
                ]
            )
        return edge

    def get_neighbors(
        self,
        node: GraphNodeRef,
        *,
        edge_type: str | None = None,
        direction: str = "out",
    ) -> list[Neighbor]:
        if direction not in {"out", "in", "both"}:
            raise GraphSchemaError(f"unknown direction: {direction!r}")
        neighbors: list[Neighbor] = []
        if direction in {"out", "both"}:
            for edge in self._edges(edge_type=edge_type, source=node):
                neighbors.append(
                    Neighbor(node=node_ref(edge.target_node_type, edge.target_node_id), edge=edge)
                )
        if direction in {"in", "both"}:
            for edge in self._edges(edge_type=edge_type, target=node):
                neighbors.append(
                    Neighbor(node=node_ref(edge.source_node_type, edge.source_node_id), edge=edge)
                )
        return neighbors

    def find_paths(
        self,
        start: GraphNodeRef,
        end: GraphNodeRef,
        *,
        max_depth: int = 3,
    ) -> list[list[object]]:
        paths: list[list[object]] = []
        frontier: list[tuple[GraphNodeRef, list[object], frozenset[GraphNodeRef]]] = [
            (start, [], frozenset({start}))
        ]
        while frontier:
            current, path, visited = frontier.pop(0)
            if len(path) >= max_depth:
                continue
            for neighbor in self.get_neighbors(current):
                if neighbor.node in visited:
                    continue
                next_path = [*path, neighbor.edge]
                if neighbor.node == end:
                    paths.append(next_path)
                    continue
                frontier.append((neighbor.node, next_path, visited | {neighbor.node}))
        return paths

    def query(
        self,
        *,
        edge_type: str | None = None,
        source: GraphNodeRef | None = None,
        target: GraphNodeRef | None = None,
        min_confidence: Decimal | None = None,
    ) -> list[object]:
        return list(
            self._edges(
                edge_type=edge_type,
                source=source,
                target=target,
                min_confidence=min_confidence,
            )
        )

    def upsert_claim(self, claim: object) -> list[object]:
        claim_node = node_ref("claim", claim.pk)
        provenance = self._record_provenance("claim", claim)
        edges = [
            self._record_edge(
                claim_node,
                node_ref("entity", claim.subject_entity_id),
                "about_subject",
                claim,
                provenance,
            ),
            self._record_edge(
                claim_node,
                node_ref("document", claim.document_id),
                "extracted_from",
                claim,
                provenance,
            ),
            self._record_edge(
                claim_node,
                node_ref("source", claim.source_id),
                "reported_by",
                claim,
                provenance,
            ),
            self._record_edge(
                claim_node,
                node_ref("evidence_span", claim.evidence_span_id),
                "supported_by",
                claim,
                provenance,
            ),
        ]
        if claim.object_entity_id is not None:
            edges.append(
                self._record_edge(
                    claim_node,
                    node_ref("entity", claim.object_entity_id),
                    "about_object",
                    claim,
                    provenance,
                )
            )
        return edges

    def upsert_event(self, event: object) -> list[object]:
        event_node = node_ref("event", event.pk)
        provenance = self._record_provenance("event", event)
        edges = [
            self._record_edge(
                event_node,
                node_ref("entity", event.actor_entity_id),
                "has_actor",
                event,
                provenance,
            ),
            self._record_edge(
                event_node,
                node_ref("document", event.document_id),
                "extracted_from",
                event,
                provenance,
            ),
            self._record_edge(
                event_node,
                node_ref("source", event.source_id),
                "reported_by",
                event,
                provenance,
            ),
            self._record_edge(
                event_node,
                node_ref("evidence_span", event.evidence_span_id),
                "supported_by",
                event,
                provenance,
            ),
        ]
        if event.object_entity_id is not None:
            edges.append(
                self._record_edge(
                    event_node,
                    node_ref("entity", event.object_entity_id),
                    "has_object",
                    event,
                    provenance,
                )
            )
        return edges

    def _record_provenance(self, record_type: str, record: object) -> dict[str, object]:
        return {
            "created_by": self.provenance_creator,
            "record_type": record_type,
            "record_id": record.pk,
            "document_id": record.document_id,
            "evidence_span_id": record.evidence_span_id,
        }

    def _record_edge(
        self,
        source: GraphNodeRef,
        target: GraphNodeRef,
        edge_type: str,
        record: object,
        provenance: dict[str, object],
    ) -> object:
        return self.add_edge(
            source,
            target,
            edge_type,
            confidence=record.confidence,
            provenance=provenance,
            source_document=record.document,
            evidence_span=record.evidence_span,
            observed_at=record.created_at,
        )

    def _edges(
        self,
        *,
        edge_type: str | None = None,
        source: GraphNodeRef | None = None,
        target: GraphNodeRef | None = None,
        min_confidence: Decimal | None = None,
    ):
        from sourceflow.models import KnowledgeEdge

        queryset = KnowledgeEdge.objects.all()
        if edge_type is not None:
            queryset = queryset.filter(edge_type=edge_type)
        if source is not None:
            queryset = queryset.filter(
                source_node_type=source.node_type,
                source_node_id=source.node_id,
            )
        if target is not None:
            queryset = queryset.filter(
                target_node_type=target.node_type,
                target_node_id=target.node_id,
            )
        if min_confidence is not None:
            queryset = queryset.filter(confidence__gte=min_confidence)
        return queryset


def default_graph_store() -> SqlGraphStore:
    """Return the default local-first SQL graph store."""
    return SqlGraphStore()
