"""Cluster-based alert evaluation and review state changes."""

from datetime import timedelta

from django.db.models import QuerySet
from django.utils import timezone

from monitoring.models import AlertHit, NormalizedDocument
from monitoring.services.alert_engine import (
    generate_recent_alerts,
    upsert_dedupe_groups,
)
from monitoring.topics import cluster_topics


def evaluate_alert_rules(lookback_hours: int = 24) -> int:
    """Run the full offline alert pipeline for recent documents.

    Example:
        `created_count = evaluate_alert_rules(lookback_hours=24)`
    """
    documents = _recent_documents(lookback_hours)
    upsert_dedupe_groups(documents)
    cluster_topics(window_hours=lookback_hours, min_documents=1)
    alerts = generate_recent_alerts(since_hours=lookback_hours, limit=100)
    return len(alerts)


def acknowledge_alert_hit(alert_hit: AlertHit) -> None:
    """Mark an alert hit acknowledged.

    Example:
        `acknowledge_alert_hit(alert_hit)`
    """
    alert_hit.status = AlertHit.Status.ACKNOWLEDGED
    alert_hit.acknowledged_at = timezone.now()
    alert_hit.save(update_fields=["status", "acknowledged_at"])


def resolve_alert_hit(alert_hit: AlertHit) -> None:
    """Mark an alert hit resolved.

    Example:
        `resolve_alert_hit(alert_hit)`
    """
    alert_hit.status = AlertHit.Status.RESOLVED
    alert_hit.resolved_at = timezone.now()
    alert_hit.save(update_fields=["status", "resolved_at"])


def ignore_alert_hit(alert_hit: AlertHit) -> None:
    """Mark an alert hit ignored.

    Example:
        `ignore_alert_hit(alert_hit)`
    """
    alert_hit.status = AlertHit.Status.IGNORED
    alert_hit.resolved_at = timezone.now()
    alert_hit.save(update_fields=["status", "resolved_at"])


def duplicate_alert_hit(alert_hit: AlertHit) -> None:
    """Mark an alert hit as a duplicate signal.

    Example:
        `duplicate_alert_hit(alert_hit)`
    """
    alert_hit.status = AlertHit.Status.DUPLICATE
    alert_hit.resolved_at = timezone.now()
    alert_hit.save(update_fields=["status", "resolved_at"])


def _recent_documents(lookback_hours: int) -> QuerySet[NormalizedDocument]:
    cutoff = timezone.now() - timedelta(hours=lookback_hours)
    return NormalizedDocument.objects.select_related("source").filter(
        created_at__gte=cutoff
    )
