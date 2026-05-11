"""Scheduling helpers for due source ingestion."""

from datetime import datetime, timedelta

from django.db.models import QuerySet

from monitoring.health import source_is_in_cooldown
from monitoring.models import IngestionCheckpoint, Source


def find_due_sources(now: datetime, limit: int | None = None) -> list[Source]:
    """Return enabled sources that are due for ingestion.

    Example:
        `sources = find_due_sources(timezone.now(), limit=20)`
    """
    sources = Source.objects.filter(is_enabled=True).order_by("name")
    due_sources = [source for source in sources if is_source_due(source, now)]
    return due_sources[:limit]


def is_source_due(source: Source, now: datetime) -> bool:
    """Return whether a source cadence has elapsed.

    Example:
        `is_source_due(source, timezone.now())`
    """
    checkpoint = _checkpoint_for_source(source)
    if source_is_in_cooldown(source):
        return False
    if checkpoint is None or checkpoint.last_attempt_at is None:
        return True
    next_run = checkpoint.last_attempt_at + timedelta(minutes=source.cadence_minutes)
    return now >= next_run


def _checkpoint_for_source(source: Source) -> IngestionCheckpoint | None:
    queryset: QuerySet[IngestionCheckpoint] = IngestionCheckpoint.objects.filter(
        source=source
    )
    return queryset.first()
