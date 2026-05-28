"""Frame-label distribution operand frames."""

from __future__ import annotations

from collections import Counter

from sourceflow.intelligence.meta_factors.common import (
    MetaFactorContext,
    cluster_memberships,
    frame_labels,
    provider_name,
)


def frame_rows(context: MetaFactorContext) -> list[dict[str, object]]:
    """Return frame labels by source, provider, and event.

    Example:
        `rows = frame_rows(context)`
    """
    rows: list[dict[str, object]] = []
    for membership in cluster_memberships(context):
        rows.extend(_frame_rows(membership))
    return rows


def frame_distribution(rows: list[dict[str, object]], key: str) -> dict[str, float]:
    """Return a normalized frame distribution for one grouping key.

    Example:
        `dist = frame_distribution(rows, "frame")`
    """
    counts = Counter(str(row[key]) for row in rows)
    total = max(1, sum(counts.values()))
    return {label: count / total for label, count in counts.items()}


def _frame_rows(membership: object) -> list[dict[str, object]]:
    return [
        {
            "frame": label,
            "event_id": membership.cluster_id,
            "source_id": membership.document.source_id,
            "provider": provider_name(membership.document),
        }
        for label in frame_labels(membership.document)
    ]
