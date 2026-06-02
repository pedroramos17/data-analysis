"""Evidence span proxy operand frames."""

from __future__ import annotations

from sourceflow.intelligence.meta_factors.common import (
    MetaFactorContext,
    cluster_memberships,
)


def evidence_rows(context: MetaFactorContext) -> list[dict[str, object]]:
    """Return evidence proxy rows from event memberships.

    Example:
        `rows = evidence_rows(context)`
    """
    return [_evidence_row(membership) for membership in cluster_memberships(context)]


def _evidence_row(membership: object) -> dict[str, object]:
    text = membership.document.content or membership.document.text or ""
    return {
        "event_id": membership.cluster_id,
        "source_id": membership.document.source_id,
        "article_id": membership.document_id,
        "evidence_span_count": max(1, text.count(".") + text.count(";")),
        "role": membership.role,
    }
