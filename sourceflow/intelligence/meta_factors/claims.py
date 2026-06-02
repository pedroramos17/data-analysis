"""Claim proxy operand frames."""

from __future__ import annotations

from collections import Counter

from monitoring.models import DocumentTopic
from sourceflow.intelligence.meta_factors.common import (
    MetaFactorContext,
    claim_labels,
    cluster_memberships,
    provider_name,
)


def claim_event_rows(context: MetaFactorContext) -> list[dict[str, object]]:
    """Return derived claim-event rows without truth judgments.

    Example:
        `rows = claim_event_rows(context)`
    """
    rows: list[dict[str, object]] = []
    for membership in cluster_memberships(context):
        rows.extend(_claim_rows(membership))
    return rows


def contradiction_counts(context: MetaFactorContext) -> dict[tuple[str, int], int]:
    """Count contradiction evidence edges by claim and event.

    Example:
        `counts = contradiction_counts(context)`
    """
    counts: Counter[tuple[str, int]] = Counter()
    for membership in cluster_memberships(context):
        _count_contradiction(counts, membership)
    return dict(counts)


def _claim_rows(membership: DocumentTopic) -> list[dict[str, object]]:
    rows = []
    for label in claim_labels(membership):
        rows.append(_claim_row(membership, label))
    return rows


def _claim_row(membership: DocumentTopic, label: str) -> dict[str, object]:
    return {
        "claim": label,
        "event_id": membership.cluster_id,
        "source_id": membership.document.source_id,
        "provider": provider_name(membership.document),
        "role": membership.role,
        "coverage": 1.0,
    }


def _count_contradiction(
    counts: Counter[tuple[str, int]],
    membership: DocumentTopic,
) -> None:
    if membership.role != DocumentTopic.Role.CONTRADICTION:
        return
    for label in claim_labels(membership):
        counts[(label, membership.cluster_id)] += 1
