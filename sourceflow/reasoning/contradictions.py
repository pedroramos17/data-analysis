"""Paraconsistent contradiction detection for canonical claims."""

from __future__ import annotations

import re
from dataclasses import dataclass
from decimal import Decimal
from typing import Iterable

from sourceflow.kg import default_graph_store, node_ref

OPPOSITE_POLARITIES = frozenset({frozenset({"positive", "negative"})})
DISPUTE_STATUS = "source_disputed"


@dataclass(frozen=True)
class ClaimKey:
    """Normalized identity for contradiction matching."""

    subject_id: str
    predicate: str
    object_key: str


@dataclass(frozen=True)
class ContradictionResult:
    """One preserved contradiction between two claims."""

    left_claim: object
    right_claim: object
    edges: tuple[object, ...]
    explanation: dict[str, object]


def claim_key(claim: object) -> ClaimKey:
    """Return the normalized subject/predicate/object key for a claim."""
    return ClaimKey(
        subject_id=str(getattr(claim, "subject_entity_id", "") or _mapping_value(claim, "subject_id")),
        predicate=_normalize(getattr(claim, "predicate", "") or _mapping_value(claim, "predicate")),
        object_key=_object_key(claim),
    )


def claims_contradict(left: object, right: object) -> bool:
    """Return whether two claims assert opposite polarity for the same fact."""
    if getattr(left, "pk", None) is not None and getattr(left, "pk", None) == getattr(right, "pk", None):
        return False
    return claim_key(left) == claim_key(right) and frozenset(
        {
            _normalize(getattr(left, "polarity", "") or _mapping_value(left, "polarity")),
            _normalize(getattr(right, "polarity", "") or _mapping_value(right, "polarity")),
        }
    ) in OPPOSITE_POLARITIES


def find_contradictory_claim_pairs(claims: Iterable[object]) -> list[tuple[object, object]]:
    """Find all unique contradictory claim pairs without mutating inputs."""
    grouped: dict[ClaimKey, list[object]] = {}
    for claim in claims:
        grouped.setdefault(claim_key(claim), []).append(claim)
    pairs: list[tuple[object, object]] = []
    for group in grouped.values():
        for left_index, left in enumerate(group):
            for right in group[left_index + 1 :]:
                if claims_contradict(left, right):
                    pairs.append((left, right))
    return pairs


def detect_claim_contradictions(
    claims: Iterable[object] | None = None,
    *,
    create_edges: bool = True,
) -> list[ContradictionResult]:
    """Mark conflicting claims as disputed and persist contradiction edges.

    This is paraconsistent: contradictory claims are preserved, no exception is
    raised, and downstream reasoning can continue over the explicit dispute
    state instead of deriving arbitrary hard truth.
    """
    from sourceflow.models import Claim

    claim_list = list(claims) if claims is not None else list(Claim.objects.filter(status=Claim.Status.ACTIVE))
    results: list[ContradictionResult] = []
    for left, right in find_contradictory_claim_pairs(claim_list):
        _mark_source_disputed(left)
        _mark_source_disputed(right)
        edges = _create_contradiction_edges(left, right) if create_edges else ()
        results.append(
            ContradictionResult(
                left_claim=left,
                right_claim=right,
                edges=edges,
                explanation=explain_contradiction(left, right),
            )
        )
    return results


def explain_contradiction(left: object, right: object) -> dict[str, object]:
    """Return a source/evidence explanation for a contradiction."""
    return {
        "status": DISPUTE_STATUS,
        "reason": "claims share subject, predicate, and object but have opposite polarity",
        "claim_key": claim_key(left).__dict__,
        "left": _claim_explanation(left),
        "right": _claim_explanation(right),
    }


def support_is_disputed(support: object) -> bool:
    """Return whether support should be treated as disputed by inference."""
    status = str(getattr(support, "status", "") or _mapping_value(support, "status"))
    metadata = _mapping_value(support, "metadata_json") if isinstance(support, dict) else getattr(support, "metadata_json", None)
    metadata = metadata or {}
    if not isinstance(metadata, dict):
        metadata = {}
    return status in {"disputed", DISPUTE_STATUS, "source_disputed"} or metadata.get("dispute_status") == DISPUTE_STATUS


def _create_contradiction_edges(left: object, right: object) -> tuple[object, ...]:
    store = default_graph_store()
    provenance = {
        "created_by": "sourceflow.reasoning.contradictions",
        "dispute_status": DISPUTE_STATUS,
        "left_claim_id": getattr(left, "pk", None),
        "right_claim_id": getattr(right, "pk", None),
    }
    confidence = min(Decimal(str(getattr(left, "confidence", 0) or 0)), Decimal(str(getattr(right, "confidence", 0) or 0)))
    return (
        store.add_edge(
            node_ref("claim", getattr(left, "pk")),
            node_ref("claim", getattr(right, "pk")),
            "contradicts",
            confidence=confidence,
            provenance=provenance,
            source_document=getattr(left, "document", None),
            evidence_span=getattr(left, "evidence_span", None),
        ),
        store.add_edge(
            node_ref("claim", getattr(right, "pk")),
            node_ref("claim", getattr(left, "pk")),
            "contradicts",
            confidence=confidence,
            provenance=provenance,
            source_document=getattr(right, "document", None),
            evidence_span=getattr(right, "evidence_span", None),
        ),
    )


def _mark_source_disputed(claim: object) -> None:
    from sourceflow.models import Claim

    metadata = dict(getattr(claim, "metadata_json", {}) or {})
    metadata["dispute_status"] = DISPUTE_STATUS
    claim.metadata_json = metadata
    claim.status = Claim.Status.DISPUTED
    claim.save(update_fields=["metadata_json", "status", "updated_at"])


def _claim_explanation(claim: object) -> dict[str, object]:
    source = getattr(claim, "source", None)
    evidence_span = getattr(claim, "evidence_span", None)
    return {
        "claim_id": getattr(claim, "pk", None),
        "polarity": getattr(claim, "polarity", ""),
        "source_id": getattr(claim, "source_id", None),
        "source_name": getattr(source, "name", ""),
        "document_id": getattr(claim, "document_id", None),
        "evidence_span_id": getattr(claim, "evidence_span_id", None),
        "evidence_text": getattr(evidence_span, "text", ""),
    }


def _object_key(claim: object) -> str:
    object_entity_id = getattr(claim, "object_entity_id", None) or _mapping_value(claim, "object_entity_id")
    if object_entity_id:
        return f"entity:{object_entity_id}"
    return f"literal:{_normalize(getattr(claim, 'object_literal', '') or _mapping_value(claim, 'object_literal') or _mapping_value(claim, 'object'))}"


def _mapping_value(value: object, key: str) -> object:
    return value.get(key, "") if isinstance(value, dict) else ""


def _normalize(value: object) -> str:
    return "_".join(re.findall(r"[a-z0-9]+", str(value).lower()))
