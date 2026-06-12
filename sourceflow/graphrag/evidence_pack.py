"""Evidence packs and proof-carrying GraphRAG answer format."""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Mapping

_CONFIDENCE_QUANTUM = Decimal("0.01")


class EvidencePackError(ValueError):
    """Raised when an answer would violate evidence requirements."""


@dataclass(frozen=True)
class EvidenceItem:
    """One serializable evidence item with provenance."""

    kind: str
    identifier: str
    text: str
    score: Decimal = Decimal("0")
    provenance: Mapping[str, object] = field(default_factory=dict)
    metadata: Mapping[str, object] = field(default_factory=dict)

    def to_dict(self) -> dict[str, object]:
        return {
            "kind": self.kind,
            "id": self.identifier,
            "text": self.text,
            "score": float(self.score),
            "provenance": dict(self.provenance),
            "metadata": dict(self.metadata),
        }


@dataclass(frozen=True)
class ConfidenceBreakdown:
    """Confidence decomposition required by proof-carrying answers."""

    retrieval_confidence: Decimal = Decimal("0")
    extraction_confidence: Decimal = Decimal("0")
    reasoning_confidence: Decimal = Decimal("0")

    @property
    def overall(self) -> Decimal:
        return ((self.retrieval_confidence + self.extraction_confidence + self.reasoning_confidence) / Decimal("3")).quantize(_CONFIDENCE_QUANTUM)

    def to_dict(self) -> dict[str, float]:
        return {
            "retrieval_confidence": float(self.retrieval_confidence),
            "extraction_confidence": float(self.extraction_confidence),
            "reasoning_confidence": float(self.reasoning_confidence),
            "overall": float(self.overall),
        }


@dataclass(frozen=True)
class EvidencePack:
    """Evidence returned by hybrid GraphRAG retrieval."""

    query: str
    text_chunks: tuple[EvidenceItem, ...] = ()
    supporting_claims: tuple[EvidenceItem, ...] = ()
    contradicting_claims: tuple[EvidenceItem, ...] = ()
    events: tuple[EvidenceItem, ...] = ()
    entities: tuple[EvidenceItem, ...] = ()
    graph_paths: tuple[EvidenceItem, ...] = ()
    assumptions_used: tuple[str, ...] = ("OWA", "PartialCWA")
    citations: tuple[Mapping[str, object], ...] = ()
    confidence: ConfidenceBreakdown = ConfidenceBreakdown()

    @property
    def has_evidence(self) -> bool:
        return any((self.text_chunks, self.supporting_claims, self.contradicting_claims, self.events, self.entities, self.graph_paths))

    def to_dict(self) -> dict[str, object]:
        return {
            "query": self.query,
            "text_chunks": [item.to_dict() for item in self.text_chunks],
            "supporting_claims": [item.to_dict() for item in self.supporting_claims],
            "contradicting_claims": [item.to_dict() for item in self.contradicting_claims],
            "events": [item.to_dict() for item in self.events],
            "entities": [item.to_dict() for item in self.entities],
            "graph_paths": [item.to_dict() for item in self.graph_paths],
            "assumptions_used": list(self.assumptions_used),
            "confidence": float(self.confidence.overall),
            "confidence_breakdown": self.confidence.to_dict(),
            "citations": [dict(citation) for citation in self.citations],
        }

    def to_answer(
        self,
        answer: str,
        *,
        what_would_change_this: tuple[str, ...] = (),
    ) -> dict[str, object]:
        """Return the proof-carrying answer format."""
        if not self.has_evidence:
            raise EvidencePackError("no answer is returned without evidence")
        return {
            "answer": answer,
            "supporting_claims": [item.to_dict() for item in self.supporting_claims],
            "contradicting_claims": [item.to_dict() for item in self.contradicting_claims],
            "events": [item.to_dict() for item in self.events],
            "entities": [item.to_dict() for item in self.entities],
            "graph_paths": [item.to_dict() for item in self.graph_paths],
            "assumptions_used": list(self.assumptions_used),
            "confidence": float(self.confidence.overall),
            "confidence_breakdown": self.confidence.to_dict(),
            "what_would_change_this": list(what_would_change_this)
            or ["new contradicting evidence", "source correction", "higher-confidence extraction"],
            "citations": [dict(citation) for citation in self.citations],
        }


def average_decimal(values: list[Decimal]) -> Decimal:
    if not values:
        return Decimal("0")
    return (sum(values, Decimal("0")) / len(values)).quantize(_CONFIDENCE_QUANTUM)
