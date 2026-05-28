"""Entity operand frames."""

from __future__ import annotations

from sourceflow.intelligence.meta_factors.common import (
    MetaFactorContext,
    cluster_memberships,
)


def entity_event_rows(context: MetaFactorContext) -> list[dict[str, object]]:
    """Return entity mentions by source and event.

    Example:
        `rows = entity_event_rows(context)`
    """
    rows: list[dict[str, object]] = []
    for membership in cluster_memberships(context):
        rows.extend(_entity_rows(membership))
    return rows


def _entity_rows(membership: object) -> list[dict[str, object]]:
    return [
        {
            "entity": str(entity),
            "event_id": membership.cluster_id,
            "source_id": membership.document.source_id,
            "mention_count": 1,
        }
        for entity in membership.document.entities
    ]
