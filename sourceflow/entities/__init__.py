"""Agentic entity extraction and linking boundary."""

from sourceflow.entities.aliases import (
    create_or_update_entity,
    exact_alias_lookup,
    external_identifier_lookup,
    normalize_alias,
    normalize_identifier,
    normalized_alias_value,
    upsert_entity_alias,
)
from sourceflow.entities.extractor import (
    EntityExtractor,
    EntityMentionCandidate,
    HeuristicEntityExtractor,
    extract_candidates,
)
from sourceflow.entities.linker import (
    EntityLinker,
    PersistedEntityMention,
    extract_link_and_persist_document_mentions,
    persist_entity_mentions,
)
from sourceflow.entities.resolution import (
    EntityLinkContext,
    EntityMergeResult,
    EntityResolution,
    fuzzy_entity_lookup,
    merge_entities,
    resolve_entity_candidate,
)

__all__ = [
    "EntityExtractor",
    "EntityLinkContext",
    "EntityLinker",
    "EntityMentionCandidate",
    "EntityMergeResult",
    "EntityResolution",
    "HeuristicEntityExtractor",
    "PersistedEntityMention",
    "create_or_update_entity",
    "exact_alias_lookup",
    "external_identifier_lookup",
    "extract_candidates",
    "extract_link_and_persist_document_mentions",
    "fuzzy_entity_lookup",
    "merge_entities",
    "normalize_alias",
    "normalize_identifier",
    "normalized_alias_value",
    "persist_entity_mentions",
    "resolve_entity_candidate",
    "upsert_entity_alias",
]
