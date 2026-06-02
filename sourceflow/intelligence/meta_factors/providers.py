"""Provider and owner operand frames."""

from __future__ import annotations

from collections import Counter

from sourceflow.intelligence.meta_factors.articles import article_event_rows
from sourceflow.intelligence.meta_factors.common import MetaFactorContext


def provider_event_rows(context: MetaFactorContext) -> list[dict[str, object]]:
    """Aggregate article rows by provider and event.

    Example:
        `rows = provider_event_rows(context)`
    """
    article_rows = article_event_rows(context)
    return _aggregate_rows(article_rows, "provider")


def owner_event_rows(context: MetaFactorContext) -> list[dict[str, object]]:
    """Aggregate article rows by owner and event.

    Example:
        `rows = owner_event_rows(context)`
    """
    article_rows = article_event_rows(context)
    return _aggregate_rows(article_rows, "owner")


def _aggregate_rows(
    article_rows: list[dict[str, object]],
    group_key: str,
) -> list[dict[str, object]]:
    counts = Counter((row[group_key], row["event_id"]) for row in article_rows)
    return [
        {group_key: key, "event_id": event_id, "article_count": count}
        for (key, event_id), count in counts.items()
    ]
