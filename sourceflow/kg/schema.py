"""Canonical knowledge graph node and edge schema.

This module is dependency-light on purpose: node references and edge-type
validation must be usable without Django so research helpers and tests can
share one auditable edge registry.
"""

from __future__ import annotations

from dataclasses import dataclass

NODE_TYPES: frozenset[str] = frozenset(
    {
        "provider_owner",
        "source",
        "document",
        "chunk",
        "evidence_span",
        "entity",
        "claim",
        "event",
        "risk_factor",
        "asset",
        "instrument",
        "portfolio",
    }
)

# Allowed (source_node_type, target_node_type) pairs per edge type. Unknown
# edge types and unknown endpoint pairs are rejected before persistence.
ALLOWED_EDGES: dict[str, frozenset[tuple[str, str]]] = {
    "published_by": frozenset({("document", "source")}),
    "owned_by": frozenset({("source", "provider_owner")}),
    "has_chunk": frozenset({("document", "chunk")}),
    "mentions": frozenset({("document", "entity"), ("chunk", "entity")}),
    "about_subject": frozenset({("claim", "entity")}),
    "about_object": frozenset({("claim", "entity")}),
    "has_actor": frozenset({("event", "entity")}),
    "has_object": frozenset({("event", "entity")}),
    "extracted_from": frozenset({("claim", "document"), ("event", "document")}),
    "reported_by": frozenset({("claim", "source"), ("event", "source")}),
    "supported_by": frozenset({("claim", "evidence_span"), ("event", "evidence_span")}),
    "contradicts": frozenset({("claim", "claim")}),
    "affects": frozenset({("event", "entity"), ("event", "asset"), ("event", "risk_factor")}),
    "exposed_to": frozenset(
        {
            ("entity", "risk_factor"),
            ("asset", "risk_factor"),
            ("portfolio", "risk_factor"),
        }
    ),
    "instrument_of": frozenset({("instrument", "asset")}),
    "holds": frozenset({("portfolio", "asset"), ("portfolio", "instrument")}),
    "issued_by": frozenset({("asset", "entity")}),
    "supplies_to": frozenset({("entity", "entity")}),
    "customer_of": frozenset({("entity", "entity")}),
}

EDGE_TYPES: frozenset[str] = frozenset(ALLOWED_EDGES)


class GraphSchemaError(ValueError):
    """Raised when a node or edge violates the canonical graph schema."""


@dataclass(frozen=True)
class GraphNodeRef:
    """Typed reference to a canonical row acting as a graph node."""

    node_type: str
    node_id: str

    def __post_init__(self) -> None:
        if self.node_type not in NODE_TYPES:
            raise GraphSchemaError(f"unknown node type: {self.node_type!r}")
        if not self.node_id:
            raise GraphSchemaError("node_id must be non-empty")


def node_ref(node_type: str, node_id: object) -> GraphNodeRef:
    """Build a validated node reference from a type and raw identifier."""
    return GraphNodeRef(node_type=node_type, node_id=str(node_id))


def is_allowed_edge(edge_type: str, source_type: str, target_type: str) -> bool:
    """Return whether the edge type allows this endpoint pair."""
    return (source_type, target_type) in ALLOWED_EDGES.get(edge_type, frozenset())


def validate_edge(edge_type: str, source: GraphNodeRef, target: GraphNodeRef) -> None:
    """Reject unknown edge types and disallowed endpoint pairs."""
    if edge_type not in ALLOWED_EDGES:
        raise GraphSchemaError(f"unknown edge type: {edge_type!r}")
    if not is_allowed_edge(edge_type, source.node_type, target.node_type):
        raise GraphSchemaError(
            f"edge type {edge_type!r} does not allow "
            f"{source.node_type!r} -> {target.node_type!r}"
        )
