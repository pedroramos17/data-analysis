"""Source reputation scoring from local operational signals."""

from datetime import datetime, timedelta
from decimal import Decimal

from django.db.models import Count, QuerySet
from django.utils import timezone

from monitoring.models import (
    AlertHit,
    DocumentEnrichment,
    IngestionCheckpoint,
    NormalizedDocument,
    Source,
    SourceReputationSnapshot,
)


def score_source_reputations(window_days: int = 30) -> int:
    """Score all sources and persist snapshots.

    Example:
        `updated_count = score_source_reputations(window_days=30)`
    """
    updated_count = 0
    window_end = timezone.now()
    window_start = window_end - timedelta(days=window_days)
    for source in Source.objects.all():
        _score_source(source, window_start, window_end)
        updated_count += 1
    return updated_count


def score_source(source: Source, window_days: int = 30) -> Decimal:
    """Score one source over a rolling window.

    Example:
        `score = score_source(source, window_days=30)`
    """
    window_end = timezone.now()
    window_start = window_end - timedelta(days=window_days)
    snapshot = _score_source(source, window_start, window_end)
    return snapshot.score


def _score_source(
    source: Source,
    window_start: datetime,
    window_end: datetime,
) -> SourceReputationSnapshot:
    components = _score_components(source, window_start, window_end)
    score = _bounded_score(_weighted_score(components))
    snapshot, _created = SourceReputationSnapshot.objects.update_or_create(
        source=source,
        window_start=window_start,
        window_end=window_end,
        defaults={"score": score, "components": components},
    )
    source.reputation_score = score
    source.reliability_score = score
    source.save(update_fields=["reputation_score", "reliability_score", "updated_at"])
    return snapshot


def _score_components(
    source: Source,
    window_start: datetime,
    window_end: datetime,
) -> dict[str, float]:
    documents = _source_documents(source, window_start, window_end)
    return {
        "tier": _tier_score(source),
        "freshness": _freshness_score(documents),
        "health": _health_score(source),
        "quality": _quality_score(documents),
        "duplicate": _duplicate_score(documents),
        "alert_noise": _alert_noise_score(source, window_start, window_end),
    }


def _weighted_score(components: dict[str, float]) -> float:
    return (
        components["tier"] * 0.25
        + components["freshness"] * 0.20
        + components["health"] * 0.20
        + components["quality"] * 0.15
        + components["duplicate"] * 0.10
        + components["alert_noise"] * 0.10
    )


def _source_documents(
    source: Source,
    window_start: datetime,
    window_end: datetime,
) -> QuerySet[NormalizedDocument]:
    return NormalizedDocument.objects.filter(
        source=source,
        created_at__gte=window_start,
        created_at__lte=window_end,
    )


def _tier_score(source: Source) -> float:
    return max(0.0, min(1.0, (5 - source.source_tier) / 4))


def _freshness_score(documents: QuerySet[NormalizedDocument]) -> float:
    return 1.0 if documents.exists() else 0.2


def _health_score(source: Source) -> float:
    checkpoint = IngestionCheckpoint.objects.filter(source=source).first()
    if checkpoint is None:
        return 0.7
    if checkpoint.cooldown_until and checkpoint.cooldown_until > timezone.now():
        return 0.2
    return max(0.0, 1.0 - min(1.0, checkpoint.consecutive_failures / 5))


def _quality_score(documents: QuerySet[NormalizedDocument]) -> float:
    enrichments = DocumentEnrichment.objects.filter(document__in=documents)
    if not enrichments.exists():
        return 0.5
    flag_count = sum(len(enrichment.quality_flags) for enrichment in enrichments)
    return max(0.0, 1.0 - min(1.0, flag_count / max(1, enrichments.count() * 4)))


def _duplicate_score(documents: QuerySet[NormalizedDocument]) -> float:
    total = documents.count()
    if total == 0:
        return 0.5
    unique = documents.values("dedupe_hash").aggregate(total=Count("dedupe_hash"))[
        "total"
    ]
    return float(unique or 0) / total


def _alert_noise_score(
    source: Source,
    window_start: datetime,
    window_end: datetime,
) -> float:
    hit_count = AlertHit.objects.filter(
        source=source,
        occurred_at__gte=window_start,
        occurred_at__lte=window_end,
    ).count()
    return max(0.0, 1.0 - min(1.0, hit_count / 10))


def _bounded_score(score: float) -> Decimal:
    return Decimal(str(round(max(0.0, min(1.0, score)), 2)))
