"""Provenance-carrying serializers for canonical sourceflow records.

Each serializer returns plain JSON-able dicts. Per the Phase 0 contract, every
extracted object must be traceable to its source evidence, so the serializers
for claims, events, beliefs, and graph edges always include a ``provenance``
block pointing back to source, document, and evidence span where available.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any


def _num(value: Any) -> Any:
    """Render Decimals as floats for clean numeric JSON; pass others through."""
    return float(value) if isinstance(value, Decimal) else value


def _iso(value: Any) -> Any:
    return value.isoformat() if hasattr(value, "isoformat") else value


def _record_provenance(record: Any) -> dict[str, Any]:
    """Common provenance for an extracted record: source/document/evidence span."""
    provenance: dict[str, Any] = {
        "source_id": getattr(record, "source_id", None),
        "document_id": getattr(record, "document_id", None),
        "evidence_span_id": getattr(record, "evidence_span_id", None),
        "extracted_by": dict(getattr(record, "provenance_json", {}) or {}),
        "created_at": _iso(getattr(record, "created_at", None)),
    }
    return provenance


def serialize_source(source: Any) -> dict[str, Any]:
    return {
        "id": source.pk,
        "name": source.name,
        "url": source.url,
        "source_type": source.source_type,
        "provider_owner_id": source.provider_owner_id,
        "country": source.country,
        "language": source.language,
        "reliability_score": _num(source.reliability_score),
        "bias_tags": list(source.bias_tags or []),
    }


def serialize_document(document: Any) -> dict[str, Any]:
    return {
        "id": document.pk,
        "source_id": document.source_id,
        "url": document.url,
        "title": document.title,
        "published_at": _iso(document.published_at),
        "ingested_at": _iso(document.ingested_at),
        "content_hash": document.content_hash,
        "language": document.language,
        "clean_text_preview": (document.clean_text or document.raw_text or "")[:280],
    }


def serialize_entity(entity: Any) -> dict[str, Any]:
    return {
        "id": entity.pk,
        "canonical_name": entity.canonical_name,
        "entity_type": entity.entity_type,
        "external_ids": dict(entity.external_ids_json or {}),
        "country": entity.country,
        "sector": entity.sector,
        "confidence": _num(entity.confidence),
    }


def serialize_evidence_span(span: Any) -> dict[str, Any]:
    if span is None:
        return {}
    return {
        "id": span.pk,
        "document_id": span.document_id,
        "chunk_id": span.chunk_id,
        "text": span.text,
        "char_start": span.char_start,
        "char_end": span.char_end,
        "extractor_name": span.extractor_name,
        "extractor_version": span.extractor_version,
        "confidence": _num(span.confidence),
    }


def serialize_claim(claim: Any, *, with_evidence: bool = False) -> dict[str, Any]:
    data = {
        "id": claim.pk,
        "subject_entity_id": claim.subject_entity_id,
        "predicate": claim.predicate,
        "object_entity_id": claim.object_entity_id,
        "object_literal": claim.object_literal,
        "polarity": claim.polarity,
        "modality": claim.modality,
        "tense": claim.tense,
        "confidence": _num(claim.confidence),
        "status": claim.status,
        "valid_from": _iso(claim.valid_from),
        "valid_until": _iso(claim.valid_until),
        "provenance": _record_provenance(claim),
    }
    if with_evidence:
        data["evidence_span"] = serialize_evidence_span(getattr(claim, "evidence_span", None))
    return data


def serialize_event(event: Any, *, with_evidence: bool = False) -> dict[str, Any]:
    data = {
        "id": event.pk,
        "actor_entity_id": event.actor_entity_id,
        "predicate": event.predicate,
        "object_entity_id": event.object_entity_id,
        "object_literal": event.object_literal,
        "event_type": event.event_type,
        "event_time": _iso(event.event_time),
        "extraction_time": _iso(event.extraction_time),
        "polarity": event.polarity,
        "magnitude": _num(event.magnitude),
        "confidence": _num(event.confidence),
        "provenance": _record_provenance(event),
    }
    if with_evidence:
        data["evidence_span"] = serialize_evidence_span(getattr(event, "evidence_span", None))
    return data


def serialize_belief(belief: Any) -> dict[str, Any]:
    return {
        "id": belief.pk,
        "belief_type": belief.belief_type,
        "subject_entity_id": belief.subject_entity_id,
        "predicate": belief.predicate,
        "object_entity_id": belief.object_entity_id,
        "object_literal": belief.object_literal,
        "truth_status": belief.truth_status,
        "confidence": _num(belief.confidence),
        "status": belief.status,
        "assumption_policy": getattr(belief.assumption_policy, "code", None),
        "created_by_rule_id": belief.created_by_rule_id,
        "provenance": dict(belief.provenance_json or {}),
    }


def serialize_justification(justification: Any) -> dict[str, Any]:
    """Serialize a justification edge and the record it points back to."""
    referent: dict[str, Any] = {}
    if justification.supporting_claim_id is not None:
        referent = {"kind": "claim", "id": justification.supporting_claim_id}
    elif justification.supporting_event_id is not None:
        referent = {"kind": "event", "id": justification.supporting_event_id}
    elif justification.supporting_belief_id is not None:
        referent = {"kind": "belief", "id": justification.supporting_belief_id}
    elif justification.rule_id is not None:
        referent = {"kind": "rule", "id": justification.rule_id}
    return {
        "id": justification.pk,
        "support_type": justification.support_type,
        "weight": _num(justification.weight),
        "rule_id": justification.rule_id,
        "referent": referent,
    }
