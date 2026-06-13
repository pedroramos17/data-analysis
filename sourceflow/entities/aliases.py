"""Canonical alias registry helpers."""

from __future__ import annotations

import re
from decimal import Decimal

ALIAS_NORMALIZE_PATTERN = re.compile(r"[^a-z0-9]+")
IDENTIFIER_TYPES = frozenset({"ticker", "isin", "lei", "cnpj"})


def normalize_alias(value: str) -> str:
    """Normalize a name-like alias for matching."""
    normalized = ALIAS_NORMALIZE_PATTERN.sub(" ", value.lower())
    return " ".join(normalized.split())


def normalize_identifier(value: str) -> str:
    """Normalize a scoped financial identifier for exact matching."""
    return re.sub(r"[^A-Z0-9]", "", value.upper())


def normalized_alias_value(value: str, alias_type: str) -> str:
    """Normalize aliases according to their type."""
    if alias_type in IDENTIFIER_TYPES:
        return normalize_identifier(value)
    return normalize_alias(value)


def upsert_entity_alias(
    entity: object,
    alias: str,
    *,
    alias_type: str = "name",
    namespace: str = "",
    metadata_json: dict[str, object] | None = None,
) -> object:
    """Create or update a canonical entity alias."""
    from sourceflow.models import EntityAlias

    alias_normalized = normalized_alias_value(alias, alias_type)
    row, _created = EntityAlias.objects.update_or_create(
        alias_normalized=alias_normalized,
        namespace=namespace.strip().upper(),
        defaults={
            "entity": entity,
            "alias": alias,
            "alias_type": alias_type,
            "metadata_json": dict(metadata_json or {}),
        },
    )
    return row


def exact_alias_lookup(alias: str, *, alias_type: str = "name", namespace: str = "") -> object | None:
    """Return an entity by exact alias and optional namespace."""
    from sourceflow.models import EntityAlias

    alias_normalized = normalized_alias_value(alias, alias_type)
    namespace_value = namespace.strip().upper()
    row = (
        EntityAlias.objects.select_related("entity")
        .filter(alias_normalized=alias_normalized, namespace=namespace_value)
        .first()
    )
    if row is None and namespace_value and alias_type not in IDENTIFIER_TYPES:
        row = (
            EntityAlias.objects.select_related("entity")
            .filter(alias_normalized=alias_normalized, namespace="")
            .first()
        )
    return row.entity if row else None


def external_identifier_lookup(identifier_type: str, value: str, *, namespace: str = "") -> object | None:
    """Return an entity by alias or JSON external identifier."""
    from sourceflow.models import Entity

    normalized = normalize_identifier(value)
    alias_match = exact_alias_lookup(normalized, alias_type=identifier_type, namespace=namespace)
    if alias_match is not None:
        return alias_match
    namespace_value = namespace.strip().upper()
    for entity in Entity.objects.all():
        identifiers = entity.external_ids_json or {}
        identifier_value = identifiers.get(identifier_type)
        if isinstance(identifier_value, dict):
            if namespace_value and str(identifier_value.get("namespace", "")).upper() != namespace_value:
                continue
            identifier_value = identifier_value.get("value")
        if identifier_value and normalize_identifier(str(identifier_value)) == normalized:
            return entity
    return None


def create_or_update_entity(
    *,
    canonical_name: str,
    entity_type: str,
    external_ids_json: dict[str, object] | None = None,
    country: str = "",
    sector: str = "",
    confidence: Decimal | str | float = Decimal("1"),
    aliases: list[dict[str, str]] | None = None,
    metadata_json: dict[str, object] | None = None,
) -> object:
    """Create or update a canonical entity and its aliases."""
    from sourceflow.models import Entity

    entity, _created = Entity.objects.update_or_create(
        canonical_name=canonical_name,
        entity_type=entity_type,
        defaults={
            "external_ids_json": dict(external_ids_json or {}),
            "country": country,
            "sector": sector,
            "confidence": Decimal(str(confidence)),
            "metadata_json": dict(metadata_json or {}),
        },
    )
    upsert_entity_alias(entity, canonical_name, alias_type="name")
    for alias_spec in aliases or []:
        upsert_entity_alias(
            entity,
            alias_spec["alias"],
            alias_type=alias_spec.get("alias_type", "name"),
            namespace=alias_spec.get("namespace", ""),
        )
    for identifier_type, identifier_value in dict(external_ids_json or {}).items():
        if identifier_type in IDENTIFIER_TYPES:
            namespace = ""
            value = identifier_value
            if isinstance(identifier_value, dict):
                namespace = str(identifier_value.get("namespace", ""))
                value = identifier_value.get("value", "")
            if value:
                upsert_entity_alias(
                    entity,
                    str(value),
                    alias_type=identifier_type,
                    namespace=namespace,
                )
    return entity
