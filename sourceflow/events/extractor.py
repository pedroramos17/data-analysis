"""Actor-predicate-object event extraction and persistence."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import Decimal
from typing import Protocol

from sourceflow.claims.extractor import ClaimCandidate, HeuristicClaimExtractor
from sourceflow.claims.normalizer import normalize_predicate
from sourceflow.entities.aliases import create_or_update_entity
from sourceflow.entities.extractor import EntityMentionCandidate
from sourceflow.entities.resolution import EntityLinkContext, resolve_entity_candidate
from sourceflow.events.classifier import classify_event_type
from sourceflow.events.impact_schema import default_event_impact
from sourceflow.ingestion.evidence import create_evidence_span_for_document


@dataclass(frozen=True)
class EventCandidate:
    """Structured market event candidate before persistence."""

    actor_text: str
    predicate: str
    object_text: str = ""
    object_literal: str = ""
    event_type: str = "other"
    event_time: datetime | None = None
    polarity: str = "unknown"
    magnitude: Decimal | None = None
    confidence: Decimal = Decimal("0.72")
    evidence_text: str = ""
    char_start: int = 0
    char_end: int = 0
    extractor_name: str = "heuristic_event_extractor"
    extractor_version: str = "1"
    metadata_json: dict[str, object] = field(default_factory=dict)


@dataclass(frozen=True)
class PersistedEventResult:
    """Persisted event plus candidate metadata."""

    event: object
    candidate: EventCandidate


class EventExtractor(Protocol):
    """Provider contract for APO event extraction."""

    def extract(self, text: str) -> list[EventCandidate]:
        """Return structured event candidates for text."""


class HeuristicEventExtractor:
    """Dependency-light fallback event extractor based on claim tuples."""

    name = "heuristic_event_extractor"
    version = "1"

    def extract(self, text: str) -> list[EventCandidate]:
        claim_candidates = HeuristicClaimExtractor().extract(text)
        return [event_candidate_from_claim(candidate) for candidate in claim_candidates]


def event_candidate_from_claim(candidate: ClaimCandidate) -> EventCandidate:
    """Convert a structured claim candidate into a market event candidate."""
    event_type = classify_event_type(candidate.predicate, candidate.object_text, candidate.evidence_text)
    impact = default_event_impact(event_type, candidate.polarity)
    return EventCandidate(
        actor_text=candidate.subject_text,
        predicate=normalize_predicate(candidate.predicate),
        object_text=candidate.object_text,
        object_literal=candidate.object_literal or candidate.object_text,
        event_type=event_type,
        event_time=None,
        polarity=candidate.polarity,
        magnitude=impact.magnitude,
        confidence=min(candidate.confidence, Decimal("0.82")),
        evidence_text=candidate.evidence_text,
        char_start=candidate.char_start,
        char_end=candidate.char_end,
        metadata_json={
            **dict(candidate.metadata_json),
            "risk_channels": list(impact.risk_channels),
            "derived_from": "claim_candidate",
        },
    )


def extract_events(text: str, extractor: EventExtractor | None = None) -> list[EventCandidate]:
    """Extract structured events using a provider or heuristic fallback."""
    active_extractor = extractor or HeuristicEventExtractor()
    return active_extractor.extract(text)


def extract_and_persist_document_events(
    document: object,
    *,
    extractor: EventExtractor | None = None,
    context: EntityLinkContext | None = None,
) -> list[PersistedEventResult]:
    """Extract and persist canonical events for a document."""
    text = getattr(document, "clean_text", "") or getattr(document, "raw_text", "")
    return persist_event_candidates(
        document,
        extract_events(text, extractor=extractor),
        context=context,
    )


def persist_event_candidates(
    document: object,
    candidates: list[EventCandidate],
    *,
    context: EntityLinkContext | None = None,
) -> list[PersistedEventResult]:
    """Persist event candidates with actor/object links and evidence."""
    from django.utils import timezone
    from sourceflow.models import Event

    results: list[PersistedEventResult] = []
    for candidate in candidates:
        actor_entity = _entity_for_text(candidate.actor_text, candidate_type="Company", context=context)
        object_entity = _object_entity_for_text(candidate.object_text, context=context)
        evidence = create_evidence_span_for_document(
            document,
            candidate.evidence_text,
            extractor_name=candidate.extractor_name,
            extractor_version=candidate.extractor_version,
            confidence=candidate.confidence,
            start_hint=candidate.char_start,
        )
        event = Event.objects.create(
            actor_entity=actor_entity,
            predicate=normalize_predicate(candidate.predicate),
            object_entity=object_entity,
            object_literal=candidate.object_literal or candidate.object_text,
            event_type=candidate.event_type,
            event_time=candidate.event_time or _published_or_none(document),
            extraction_time=timezone.now(),
            polarity=candidate.polarity,
            magnitude=candidate.magnitude,
            confidence=candidate.confidence,
            source_id=getattr(document, "source_id"),
            document=document,
            evidence_span=evidence,
            metadata_json={
                **dict(candidate.metadata_json),
                "actor_text": candidate.actor_text,
                "object_text": candidate.object_text,
            },
            provenance_json={"created_by": "sourceflow.events.extractor"},
        )
        results.append(PersistedEventResult(event=event, candidate=candidate))
    return results


def _entity_for_text(text: str, *, candidate_type: str, context: EntityLinkContext | None) -> object:
    candidate = EntityMentionCandidate(
        text=text,
        entity_type=candidate_type,
        char_start=0,
        char_end=len(text),
        confidence=Decimal("0.80"),
    )
    resolution = resolve_entity_candidate(candidate, context)
    if resolution.entity is not None:
        return resolution.entity
    return create_or_update_entity(
        canonical_name=text,
        entity_type=candidate_type,
        confidence=Decimal("0.50"),
        metadata_json={"nil_candidate": True, "nil_reason": resolution.nil_reason},
    )


def _object_entity_for_text(text: str, context: EntityLinkContext | None) -> object | None:
    if not text or len(text.split()) > 4 or not text[:1].isupper():
        return None
    candidate = EntityMentionCandidate(
        text=text,
        entity_type="Company",
        char_start=0,
        char_end=len(text),
        confidence=Decimal("0.65"),
    )
    return resolve_entity_candidate(candidate, context).entity


def _published_or_none(document: object) -> datetime | None:
    value = getattr(document, "published_at", None)
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value
