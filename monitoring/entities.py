"""Canonical entity resolution and co-occurrence graph scaffolding."""

import re
from itertools import combinations

from django.utils import timezone

from monitoring.models import (
    CanonicalEntity,
    DocumentEntity,
    EntityAlias,
    EntityRelationship,
    NormalizedDocument,
)

ENTITY_NAME_PATTERN = re.compile(r"[^a-z0-9]+")


def index_document_entities(document: NormalizedDocument) -> int:
    """Resolve extracted document entities and update co-occurrence edges.

    Example:
        `indexed_count = index_document_entities(document)`
    """
    entities = [_resolve_entity(name) for name in _document_entity_names(document)]
    for entity in entities:
        _upsert_document_entity(document, entity)
    _upsert_relationships(entities)
    return len(entities)


def normalize_entity_name(name: str) -> str:
    """Normalize an entity surface form for matching.

    Example:
        `normalize_entity_name("OpenAI, Inc.")`
    """
    normalized = ENTITY_NAME_PATTERN.sub(" ", name.lower())
    return " ".join(normalized.split())


def _document_entity_names(document: NormalizedDocument) -> tuple[str, ...]:
    names = [str(name).strip() for name in document.entities if str(name).strip()]
    return tuple(dict.fromkeys(names))


def _resolve_entity(name: str) -> CanonicalEntity:
    normalized_name = normalize_entity_name(name)
    alias = EntityAlias.objects.filter(alias_normalized=normalized_name).first()
    if alias is not None:
        return alias.entity
    entity, created = CanonicalEntity.objects.get_or_create(
        normalized_name=normalized_name,
        defaults={"name": name},
    )
    if created:
        EntityAlias.objects.create(
            entity=entity, alias=name, alias_normalized=normalized_name
        )
    return entity


def _upsert_document_entity(
    document: NormalizedDocument,
    entity: CanonicalEntity,
) -> None:
    DocumentEntity.objects.update_or_create(
        document=document,
        entity=entity,
        defaults={"mention_text": entity.name, "mention_count": 1},
    )


def _upsert_relationships(entities: list[CanonicalEntity]) -> None:
    for left_entity, right_entity in combinations(_ordered_entities(entities), 2):
        _upsert_relationship(left_entity, right_entity)


def _ordered_entities(entities: list[CanonicalEntity]) -> list[CanonicalEntity]:
    unique_entities = {entity.id: entity for entity in entities}
    return [unique_entities[key] for key in sorted(unique_entities)]


def _upsert_relationship(
    source_entity: CanonicalEntity,
    target_entity: CanonicalEntity,
) -> None:
    relationship, created = EntityRelationship.objects.get_or_create(
        source_entity=source_entity,
        target_entity=target_entity,
        relationship_type="co_occurs",
    )
    if created:
        return
    relationship.weight += 1
    relationship.last_seen_at = timezone.now()
    relationship.save(update_fields=["weight", "last_seen_at"])
