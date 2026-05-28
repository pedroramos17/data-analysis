"""Article-level operand frames."""

from __future__ import annotations

from sourceflow.intelligence.meta_factors.common import (
    MetaFactorContext,
    cluster_memberships,
    document_available_at,
    owner_name,
    peer_group,
    provider_name,
)


def article_event_rows(context: MetaFactorContext) -> list[dict[str, object]]:
    """Return article-event rows available at timestamp t.

    Example:
        `rows = article_event_rows(context)`
    """
    rows: list[dict[str, object]] = []
    for membership in cluster_memberships(context):
        rows.append(_article_row(membership))
    return rows


def _article_row(membership: object) -> dict[str, object]:
    document = membership.document
    source = document.source
    return {
        "event_id": membership.cluster_id,
        "source_id": source.id,
        "article_id": document.id,
        "provider": provider_name(document),
        "owner": owner_name(document),
        "peer_group": peer_group(document),
        "article_reach_weight": float(source.reputation_score or 1) or 1.0,
        "available_at": document_available_at(document),
    }
