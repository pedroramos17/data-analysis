"""Entity linker and persistence helpers."""

from __future__ import annotations

from dataclasses import dataclass

from decimal import Decimal

from sourceflow.entities.extractor import EntityExtractor, EntityMentionCandidate, extract_candidates
from sourceflow.entities.resolution import EntityLinkContext, EntityResolution, resolve_entity_candidate


@dataclass(frozen=True)
class PersistedEntityMention:
    """A persisted entity mention plus resolution metadata."""

    mention: object
    resolution: EntityResolution


class EntityLinker:
    """Resolve entity mention candidates to canonical entities or NIL candidates."""

    def link(
        self,
        candidate: EntityMentionCandidate,
        context: EntityLinkContext | None = None,
    ) -> EntityResolution:
        return resolve_entity_candidate(candidate, context)

    def link_many(
        self,
        candidates: list[EntityMentionCandidate],
        context: EntityLinkContext | None = None,
    ) -> list[EntityResolution]:
        return [self.link(candidate, context) for candidate in candidates]


def extract_link_and_persist_document_mentions(
    document: object,
    *,
    extractor: EntityExtractor | None = None,
    linker: EntityLinker | None = None,
    context: EntityLinkContext | None = None,
) -> list[PersistedEntityMention]:
    """Extract, resolve, and persist canonical entity mentions for a document."""
    text = getattr(document, "clean_text", "") or getattr(document, "raw_text", "")
    candidates = extract_candidates(text, extractor=extractor)
    return persist_entity_mentions(
        document,
        candidates,
        linker=linker,
        context=context,
    )


def persist_entity_mentions(
    document: object,
    candidates: list[EntityMentionCandidate],
    *,
    linker: EntityLinker | None = None,
    context: EntityLinkContext | None = None,
) -> list[PersistedEntityMention]:
    """Persist candidate mentions with linked entity or NIL status."""
    from sourceflow.models import EntityMention, EvidenceSpan

    active_linker = linker or EntityLinker()
    persisted: list[PersistedEntityMention] = []
    for candidate in candidates:
        resolution = active_linker.link(candidate, context)
        chunk = _chunk_for_document_span(document, candidate.char_start, candidate.char_end)
        evidence = EvidenceSpan.objects.create(
            source_id=getattr(document, "source_id"),
            document=document,
            chunk=chunk,
            text=candidate.text,
            char_start=candidate.char_start,
            char_end=candidate.char_end,
            extractor_name=candidate.extractor_name,
            extractor_version=candidate.extractor_version,
            confidence=candidate.confidence,
            metadata_json={"entity_type": candidate.entity_type},
            provenance_json={"created_by": "sourceflow.entities.linker"},
        )
        metadata = {
            **dict(candidate.metadata_json),
            "resolution_strategy": resolution.strategy,
            "assumption_policy": resolution.assumption_policy.value,
        }
        if resolution.is_nil:
            metadata["nil_reason"] = resolution.nil_reason
        mention = EntityMention.objects.create(
            document=document,
            chunk=chunk,
            entity=resolution.entity,
            evidence_span=evidence,
            mention_text=candidate.text,
            entity_type=candidate.entity_type,
            char_start=candidate.char_start,
            char_end=candidate.char_end,
            confidence=_max_decimal(candidate.confidence, resolution.confidence),
            extractor_name=candidate.extractor_name,
            extractor_version=candidate.extractor_version,
            status="nil_candidate" if resolution.is_nil else "linked",
            metadata_json=metadata,
            provenance_json={"created_by": "sourceflow.entities.linker"},
        )
        persisted.append(PersistedEntityMention(mention=mention, resolution=resolution))
    return persisted


def _chunk_for_document_span(document: object, char_start: int, char_end: int) -> object | None:
    for chunk in document.chunks.order_by("chunk_index"):
        if chunk.char_start <= char_start and char_end <= chunk.char_end:
            return chunk
    for chunk in document.chunks.order_by("chunk_index"):
        if chunk.char_start <= char_start < chunk.char_end:
            return chunk
    return None


def _max_decimal(left: Decimal, right: Decimal) -> Decimal:
    return left if left >= right else right
