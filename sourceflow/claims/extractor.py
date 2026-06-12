"""Structured claim extraction and persistence."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Protocol

from sourceflow.claims.normalizer import (
    infer_modality,
    infer_polarity,
    infer_tense,
    normalize_object_literal,
    normalize_predicate,
)
from sourceflow.claims.validators import ClaimValidationResult, validate_claim_candidate
from sourceflow.entities.aliases import create_or_update_entity
from sourceflow.entities.extractor import EntityMentionCandidate
from sourceflow.entities.resolution import EntityLinkContext, resolve_entity_candidate
from sourceflow.ingestion.evidence import create_evidence_span_for_document

CLAIM_PATTERN = re.compile(
    r"(?P<subject>[A-Z][A-Za-z0-9&.-]*(?:\s+[A-Z][A-Za-z0-9&.-]*){0,3})\s+"
    r"(?P<predicate>faces|reports|signals|denies|confirms|alleges|expects|forecasts|announces|launches|cuts|raises|settles|sues|acquires|warns|delays)\s+"
    r"(?P<object>[^.!?;]+)",
    re.IGNORECASE,
)
SENTENCE_PATTERN = re.compile(r"[^.!?]+[.!?]?")


@dataclass(frozen=True)
class ClaimCandidate:
    """Structured claim candidate before persistence."""

    subject_text: str
    predicate: str
    object_text: str = ""
    object_literal: str = ""
    polarity: str = "unknown"
    modality: str = "asserted"
    tense: str = "present"
    confidence: Decimal = Decimal("0.75")
    evidence_text: str = ""
    char_start: int = 0
    char_end: int = 0
    extractor_name: str = "heuristic_claim_extractor"
    extractor_version: str = "1"
    metadata_json: dict[str, object] = field(default_factory=dict)


@dataclass(frozen=True)
class PersistedClaimResult:
    """Persisted claim plus validation metadata."""

    claim: object | None
    candidate: ClaimCandidate
    validation: ClaimValidationResult


class ClaimExtractor(Protocol):
    """Provider contract for structured claim extraction."""

    def extract(self, text: str) -> list[ClaimCandidate]:
        """Return structured claim candidates for text."""


class HeuristicClaimExtractor:
    """Dependency-light fallback extractor for simple APO-style claims."""

    name = "heuristic_claim_extractor"
    version = "1"

    def extract(self, text: str) -> list[ClaimCandidate]:
        candidates: list[ClaimCandidate] = []
        for sentence_match in SENTENCE_PATTERN.finditer(text):
            sentence = sentence_match.group(0).strip()
            if not sentence:
                continue
            candidates.extend(_claims_from_sentence(sentence, sentence_match.start()))
        return candidates


def extract_claims(text: str, extractor: ClaimExtractor | None = None) -> list[ClaimCandidate]:
    """Extract structured claims using a provider or heuristic fallback."""
    active_extractor = extractor or HeuristicClaimExtractor()
    return active_extractor.extract(text)


def extract_and_persist_document_claims(
    document: object,
    *,
    extractor: ClaimExtractor | None = None,
    context: EntityLinkContext | None = None,
    persist_incomplete: bool = False,
) -> list[PersistedClaimResult]:
    """Extract and persist canonical claims for a document."""
    text = getattr(document, "clean_text", "") or getattr(document, "raw_text", "")
    return persist_claim_candidates(
        document,
        extract_claims(text, extractor=extractor),
        context=context,
        persist_incomplete=persist_incomplete,
    )


def persist_claim_candidates(
    document: object,
    candidates: list[ClaimCandidate],
    *,
    context: EntityLinkContext | None = None,
    persist_incomplete: bool = False,
) -> list[PersistedClaimResult]:
    """Validate and persist claim candidates."""
    from sourceflow.models import Claim

    results: list[PersistedClaimResult] = []
    for candidate in candidates:
        validation = validate_claim_candidate(candidate)
        if not validation.is_valid and not persist_incomplete:
            results.append(PersistedClaimResult(None, candidate, validation))
            continue
        subject_entity = _entity_for_text(candidate.subject_text, candidate_type="Company", context=context)
        object_entity = _object_entity_for_text(candidate.object_text, context=context)
        evidence = create_evidence_span_for_document(
            document,
            candidate.evidence_text,
            extractor_name=candidate.extractor_name,
            extractor_version=candidate.extractor_version,
            confidence=candidate.confidence,
            start_hint=candidate.char_start,
        )
        claim = Claim.objects.create(
            subject_entity=subject_entity,
            predicate=normalize_predicate(candidate.predicate),
            object_entity=object_entity,
            object_literal=candidate.object_literal or candidate.object_text,
            polarity=candidate.polarity,
            modality=candidate.modality,
            tense=candidate.tense,
            confidence=candidate.confidence,
            source_id=getattr(document, "source_id"),
            document=document,
            evidence_span=evidence,
            status=validation.status,
            metadata_json={
                **dict(candidate.metadata_json),
                "subject_text": candidate.subject_text,
                "object_text": candidate.object_text,
                "validation_errors": list(validation.errors),
            },
            provenance_json={"created_by": "sourceflow.claims.extractor"},
        )
        results.append(PersistedClaimResult(claim, candidate, validation))
    return results


def _claims_from_sentence(sentence: str, sentence_start: int) -> list[ClaimCandidate]:
    candidates: list[ClaimCandidate] = []
    for match in CLAIM_PATTERN.finditer(sentence):
        subject = match.group("subject").strip()
        predicate = normalize_predicate(match.group("predicate"))
        object_text = normalize_object_literal(match.group("object"))
        evidence = sentence.strip()
        candidates.append(
            ClaimCandidate(
                subject_text=subject,
                predicate=predicate,
                object_text=object_text,
                object_literal=object_text,
                polarity=infer_polarity(predicate, object_text, evidence),
                modality=infer_modality(predicate, evidence),
                tense=infer_tense(evidence),
                confidence=Decimal("0.78"),
                evidence_text=evidence,
                char_start=sentence_start + match.start(),
                char_end=sentence_start + len(evidence),
                metadata_json={"pattern": "simple_apo"},
            )
        )
    return candidates


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
    if not text or not re.match(r"^[A-Z][A-Za-z0-9&.-]*(?:\s+[A-Z][A-Za-z0-9&.-]*){0,3}$", text):
        return None
    candidate = EntityMentionCandidate(
        text=text,
        entity_type="Company",
        char_start=0,
        char_end=len(text),
        confidence=Decimal("0.65"),
    )
    resolution = resolve_entity_candidate(candidate, context)
    return resolution.entity
