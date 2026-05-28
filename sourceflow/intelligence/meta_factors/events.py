"""Event-level operand frames."""

from __future__ import annotations

from sourceflow.intelligence.meta_factors.common import (
    MetaFactorContext,
    event_clusters,
)


def event_rows(context: MetaFactorContext) -> list[dict[str, object]]:
    """Return event rows with stored cluster metrics.

    Example:
        `rows = event_rows(context)`
    """
    return [_event_row(cluster) for cluster in event_clusters(context)]


def _event_row(cluster: object) -> dict[str, object]:
    return {
        "event_id": cluster.id,
        "event_source_count": cluster.source_count,
        "event_document_count": cluster.document_count,
        "trend_score": float(cluster.trend_score or 0),
        "frame_labels": list(cluster.keywords or []),
        "available_at": cluster.created_at,
    }
