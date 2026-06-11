"""Entity resolution, NIL support, and merge workflow."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from difflib import SequenceMatcher

from sourceflow.entities.aliases import (
    external_identifier_lookup,
    exact_alias_lookup,
    normalize_alias,
    normalize_identifier,
    upsert_entity_alias,
)
from sourceflow.entities.extractor import EntityMentionCandidate
from sourceflow.reasoning.assumptions import AssumptionPolicyCode

IDENTIFIER_TYPES = frozenset({"ticker", "isin", "lei", "cnpj"})
FUZZY_THRESHOLD = 0.86
COMPANY_SUFFIXES = (" inc", " incorporated", " corp", " corporation", " ltd", " limited", " sa", " s a")


@dataclass(frozen=True)
class EntityLinkContext:
    """Context used to disambiguate aliases and identifiers."""

    exchange: str = ""
    country: str = ""
    sector: str = ""
    document_id: int | None = None
    source_id: int | None = None


@dataclass(frozen=True)
class EntityResolution:
    """Result of resolving one entity mention candidate."""

    candidate: EntityMentionCandidate
    entity: object | None
    strategy: str
    confidence: Decimal
    is_nil: bool
    assumption_policy: AssumptionPolicyCode
    nil_reason: str = ""


@dataclass(frozen=True)
class EntityMergeResult:
    """Summary of an entity merge workflow."""

    primary_entity_id: int
    duplicate_entity_id: int
    aliases_moved: int
    mentions_updated: int
    claims_updated: int
    events_updated: int
    beliefs_updated: int


def resolve_entity_candidate(
    candidate: EntityMentionCandidate,
    context: EntityLinkContext | None = None,
) -> EntityResolution:
    """Resolve a candidate to a canonical entity or NIL candidate."""
    active_context = context or EntityLinkContext()
    identifier_type = _candidate_identifier_type(candidate)
    if identifier_type:
        entity = external_identifier_lookup(
            identifier_type,
            candidate.text,
            namespace=_identifier_namespace(candidate, active_context),
        )
        if entity is not None:
            return EntityResolution(
                candidate=candidate,
                entity=entity,
                strategy=f"{identifier_type}_exact",
                confidence=max(candidate.confidence, Decimal("0.95")),
                is_nil=False,
                assumption_policy=AssumptionPolicyCode.UNIQUE_NAME,
            )

    entity = exact_alias_lookup(candidate.text, alias_type="name")
    if entity is not None:
        return EntityResolution(
            candidate=candidate,
            entity=entity,
            strategy="alias_exact",
            confidence=max(candidate.confidence, Decimal("0.90")),
            is_nil=False,
            assumption_policy=AssumptionPolicyCode.NO_UNIQUE_NAME,
        )

    fuzzy_entity, fuzzy_score = fuzzy_entity_lookup(candidate.text, entity_type=candidate.entity_type)
    if fuzzy_entity is not None:
        return EntityResolution(
            candidate=candidate,
            entity=fuzzy_entity,
            strategy="name_fuzzy",
            confidence=max(candidate.confidence, Decimal(str(round(fuzzy_score, 2)))),
            is_nil=False,
            assumption_policy=AssumptionPolicyCode.NO_UNIQUE_NAME,
        )

    return EntityResolution(
        candidate=candidate,
        entity=None,
        strategy="nil_candidate",
        confidence=candidate.confidence,
        is_nil=True,
        assumption_policy=AssumptionPolicyCode.NO_UNIQUE_NAME,
        nil_reason="no_canonical_entity_match",
    )


def fuzzy_entity_lookup(text: str, *, entity_type: str = "", threshold: float = FUZZY_THRESHOLD) -> tuple[object | None, float]:
    """Return the closest entity by normalized name similarity."""
    from sourceflow.models import Entity

    query = _company_match_key(text)
    best_entity = None
    best_score = 0.0
    queryset = Entity.objects.all()
    if entity_type and entity_type not in {"Unknown", "Security"}:
        queryset = queryset.filter(entity_type=entity_type)
    for entity in queryset:
        score = SequenceMatcher(None, query, _company_match_key(entity.canonical_name)).ratio()
        if score > best_score:
            best_entity = entity
            best_score = score
    if best_entity is None or best_score < threshold:
        return None, best_score
    return best_entity, best_score


def merge_entities(primary_entity: object, duplicate_entity: object, *, reason: str = "") -> EntityMergeResult:
    """Merge duplicate entity references into a primary entity."""
    from sourceflow.models import Belief, Claim, EntityAlias, EntityMention, Event, RetractionLog

    if primary_entity.pk == duplicate_entity.pk:
        return EntityMergeResult(primary_entity.pk, duplicate_entity.pk, 0, 0, 0, 0, 0)

    aliases_moved = 0
    for alias in list(EntityAlias.objects.filter(entity=duplicate_entity)):
        existing = EntityAlias.objects.filter(
            alias_normalized=alias.alias_normalized,
            namespace=alias.namespace,
        ).exclude(pk=alias.pk).first()
        if existing is None:
            alias.entity = primary_entity
            alias.save(update_fields=["entity", "updated_at"])
            aliases_moved += 1
        else:
            alias.delete()

    mentions_updated = EntityMention.objects.filter(entity=duplicate_entity).update(entity=primary_entity)
    claims_updated = Claim.objects.filter(subject_entity=duplicate_entity).update(subject_entity=primary_entity)
    claims_updated += Claim.objects.filter(object_entity=duplicate_entity).update(object_entity=primary_entity)
    events_updated = Event.objects.filter(actor_entity=duplicate_entity).update(actor_entity=primary_entity)
    events_updated += Event.objects.filter(object_entity=duplicate_entity).update(object_entity=primary_entity)
    beliefs_updated = Belief.objects.filter(subject_entity=duplicate_entity).update(subject_entity=primary_entity)
    beliefs_updated += Belief.objects.filter(object_entity=duplicate_entity).update(object_entity=primary_entity)
    duplicate_entity.metadata_json = {
        **dict(duplicate_entity.metadata_json or {}),
        "merged_into_entity_id": primary_entity.pk,
        "merge_reason": reason,
    }
    duplicate_entity.save(update_fields=["metadata_json", "updated_at"])
    RetractionLog.objects.create(
        target_type="entity",
        target_id=str(duplicate_entity.pk),
        reason=reason or "entity merge",
        previous_status="active",
        new_status="merged",
        metadata_json={"primary_entity_id": primary_entity.pk},
    )
    return EntityMergeResult(
        primary_entity_id=primary_entity.pk,
        duplicate_entity_id=duplicate_entity.pk,
        aliases_moved=aliases_moved,
        mentions_updated=mentions_updated,
        claims_updated=claims_updated,
        events_updated=events_updated,
        beliefs_updated=beliefs_updated,
    )


def _candidate_identifier_type(candidate: EntityMentionCandidate) -> str:
    value = str(candidate.metadata_json.get("identifier_type", ""))
    if value in IDENTIFIER_TYPES:
        return value
    if candidate.entity_type == "Security" and candidate.text == normalize_identifier(candidate.text):
        return "ticker"
    return ""


def _identifier_namespace(candidate: EntityMentionCandidate, context: EntityLinkContext) -> str:
    return str(candidate.metadata_json.get("namespace") or context.exchange or "").strip().upper()


def _company_match_key(value: str) -> str:
    normalized = normalize_alias(value)
    for suffix in COMPANY_SUFFIXES:
        if normalized.endswith(suffix):
            return normalized[: -len(suffix)].strip()
    return normalized
