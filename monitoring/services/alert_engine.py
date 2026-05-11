"""Offline alert engine for event-cluster signal generation."""

from __future__ import annotations

from dataclasses import asdict
from datetime import timedelta
from decimal import Decimal

from django.db.models import QuerySet
from django.utils import timezone

from monitoring.models import (
    AlertDetector,
    AlertHit,
    AlertHitDocument,
    AlertRule,
    DedupeGroup,
    EventCluster,
    EventClusterDocument,
    NormalizedDocument,
)
from monitoring.services.alert_scoring import (
    AlertScoreBreakdown,
    build_alert_explanation,
    calculate_alert_score,
    calculate_novelty_score,
    calculate_source_diversity,
    calculate_trend_score,
    compute_content_hash,
    compute_simhash,
    entity_importance_score,
    map_score_to_severity,
    market_relevance_score,
    normalize_text,
)


def generate_alerts_for_cluster(
    cluster_id: int,
    dry_run: bool = False,
) -> list[AlertHit]:
    """Generate deduplicated alert hits for one event cluster.

    Example:
        `alerts = generate_alerts_for_cluster(1)`
    """
    cluster = EventCluster.objects.get(pk=cluster_id)
    documents = _cluster_documents(cluster)
    if not dry_run:
        ensure_default_detectors()
    alerts = _rule_alerts(cluster, documents, dry_run)
    alerts.extend(_detector_alerts(cluster, documents, dry_run))
    return alerts


def generate_recent_alerts(
    since_hours: int = 24,
    limit: int = 100,
    dry_run: bool = False,
) -> list[AlertHit]:
    """Generate alerts for recently updated active clusters.

    Example:
        `alerts = generate_recent_alerts(since_hours=24)`
    """
    cutoff = timezone.now() - timedelta(hours=since_hours)
    clusters = EventCluster.objects.filter(updated_at__gte=cutoff)[:limit]
    alerts: list[AlertHit] = []
    for cluster in clusters:
        alerts.extend(generate_alerts_for_cluster(cluster.id, dry_run=dry_run))
    return alerts


def ensure_default_detectors() -> int:
    """Create default automatic detector configs if missing.

    Example:
        `created_count = ensure_default_detectors()`
    """
    created_count = 0
    for detector_spec in _default_detector_specs():
        _detector, created = AlertDetector.objects.get_or_create(
            name=detector_spec["name"], defaults=detector_spec
        )
        created_count += int(created)
    return created_count


def upsert_dedupe_groups(documents: QuerySet[NormalizedDocument]) -> int:
    """Create exact dedupe groups for recent documents.

    Example:
        `count = upsert_dedupe_groups(NormalizedDocument.objects.all())`
    """
    updated_count = 0
    for document in documents:
        _update_document_hashes(document)
        _upsert_exact_group(document)
        updated_count += 1
    return updated_count


def _rule_alerts(
    cluster: EventCluster,
    documents: list[NormalizedDocument],
    dry_run: bool,
) -> list[AlertHit]:
    alerts: list[AlertHit] = []
    for rule in _enabled_rules():
        if _rule_matches_cluster(rule, cluster, documents):
            alerts.extend(_materialize_alert(cluster, documents, rule, None, dry_run))
    return alerts


def _detector_alerts(
    cluster: EventCluster,
    documents: list[NormalizedDocument],
    dry_run: bool,
) -> list[AlertHit]:
    alerts: list[AlertHit] = []
    for detector in AlertDetector.objects.filter(enabled=True):
        if _detector_matches_cluster(detector, cluster, documents):
            alerts.extend(
                _materialize_alert(cluster, documents, None, detector, dry_run)
            )
    return alerts


def _materialize_alert(
    cluster: EventCluster,
    documents: list[NormalizedDocument],
    rule: AlertRule | None,
    detector: AlertDetector | None,
    dry_run: bool,
) -> list[AlertHit]:
    breakdown = _score_breakdown(cluster, documents, rule, detector)
    score = calculate_alert_score(breakdown)
    if score < 0.30:
        return []
    dedupe_key = _alert_dedupe_key(cluster, rule, detector)
    alert = _build_alert(
        cluster, documents, rule, detector, breakdown, score, dedupe_key
    )
    if dry_run:
        return [alert]
    persisted, created = _persist_alert(alert)
    if created:
        _persist_alert_documents(persisted, cluster, documents)
    return [persisted] if created else []


def _build_alert(
    cluster: EventCluster,
    documents: list[NormalizedDocument],
    rule: AlertRule | None,
    detector: AlertDetector | None,
    breakdown: AlertScoreBreakdown,
    score: float,
    dedupe_key: str,
) -> AlertHit:
    representative = documents[0] if documents else None
    return AlertHit(
        rule=rule,
        detector=detector,
        cluster=cluster,
        representative_document=representative,
        document=representative,
        source=representative.source if representative else None,
        dedupe_hash=compute_content_hash(dedupe_key),
        dedupe_key=dedupe_key,
        trigger_type=_trigger_type(rule, detector),
        title=_cluster_title(cluster),
        explanation=build_alert_explanation(cluster, rule, detector, breakdown),
        severity=map_score_to_severity(score),
        matched_text=_matched_text(cluster, rule, detector),
        severity_score=_decimal(score),
        confidence_score=_decimal(cluster.confidence_score),
        novelty_score=_decimal(breakdown.novelty),
        trend_score=_decimal(breakdown.trend),
        source_diversity_score=_decimal(breakdown.source_diversity),
        entity_importance_score=_decimal(breakdown.entity_importance),
        market_relevance_score=_decimal(breakdown.market_relevance),
        metadata={"score_breakdown": asdict(breakdown)},
    )


def _persist_alert(alert: AlertHit) -> tuple[AlertHit, bool]:
    return AlertHit.objects.get_or_create(
        dedupe_key=alert.dedupe_key,
        defaults=_alert_defaults(alert),
    )


def _persist_alert_documents(
    alert: AlertHit,
    cluster: EventCluster,
    documents: list[NormalizedDocument],
) -> None:
    memberships = _membership_by_document(cluster)
    for document in documents:
        membership = memberships.get(document.id)
        AlertHitDocument.objects.get_or_create(
            alert_hit=alert,
            document=document,
            defaults=_alert_document_defaults(document, membership),
        )


def _alert_defaults(alert: AlertHit) -> dict[str, object]:
    return {
        field.name: getattr(alert, field.name)
        for field in AlertHit._meta.fields
        if field.name != "id"
    }


def _alert_document_defaults(
    document: NormalizedDocument,
    membership: EventClusterDocument | None,
) -> dict[str, object]:
    return {
        "role": membership.role if membership else EventClusterDocument.Role.EVIDENCE,
        "similarity_to_cluster": membership.similarity if membership else Decimal("0"),
        "source_reliability_score": _document_reliability(document),
        "matched_text": document.title[:500],
    }


def _cluster_documents(cluster: EventCluster) -> list[NormalizedDocument]:
    memberships = EventClusterDocument.objects.filter(cluster=cluster).select_related(
        "document", "document__source"
    )
    return [membership.document for membership in memberships]


def _membership_by_document(cluster: EventCluster) -> dict[int, EventClusterDocument]:
    memberships = EventClusterDocument.objects.filter(cluster=cluster)
    return {membership.document_id: membership for membership in memberships}


def _score_breakdown(
    cluster: EventCluster,
    documents: list[NormalizedDocument],
    rule: AlertRule | None,
    detector: AlertDetector | None,
) -> AlertScoreBreakdown:
    return AlertScoreBreakdown(
        rule_match=_rule_or_detector_score(rule, detector),
        trend=calculate_trend_score(cluster),
        novelty=calculate_novelty_score(cluster),
        source_diversity=calculate_source_diversity(documents),
        entity_importance=entity_importance_score(cluster),
        market_relevance=market_relevance_score(cluster),
        reliability=_reliability_score(documents),
    )


def _enabled_rules() -> QuerySet[AlertRule]:
    return AlertRule.objects.filter(is_enabled=True, enabled=True)


def _rule_matches_cluster(
    rule: AlertRule,
    cluster: EventCluster,
    documents: list[NormalizedDocument],
) -> bool:
    if not _rule_thresholds_match(rule, cluster):
        return False
    if rule.rule_type == AlertRule.RuleType.VOLUME:
        return cluster.document_count >= rule.threshold_count
    return _query_matches(rule, cluster, documents) or _filters_match(rule, documents)


def _rule_thresholds_match(rule: AlertRule, cluster: EventCluster) -> bool:
    return (
        cluster.severity_score >= rule.min_severity
        and cluster.novelty_score >= rule.min_novelty
        and cluster.trend_score >= rule.min_trend
    )


def _query_matches(
    rule: AlertRule,
    cluster: EventCluster,
    documents: list[NormalizedDocument],
) -> bool:
    query = rule.query.lower().strip()
    if not query and rule.rule_type != AlertRule.RuleType.CATEGORY:
        return False
    if rule.rule_type == AlertRule.RuleType.CATEGORY:
        return any(document.source.category == rule.category for document in documents)
    return query in _cluster_search_text(cluster, documents)


def _filters_match(rule: AlertRule, documents: list[NormalizedDocument]) -> bool:
    entities = {str(entity).lower() for doc in documents for entity in doc.entities}
    topics = {str(tag).lower() for doc in documents for tag in doc.tags}
    sources = {str(doc.source_id) for doc in documents}
    return (
        _overlaps(rule.entity_filters, entities)
        or _overlaps(rule.topic_filters, topics)
        or _overlaps(rule.source_filters, sources)
    )


def _detector_matches_cluster(
    detector: AlertDetector,
    cluster: EventCluster,
    documents: list[NormalizedDocument],
) -> bool:
    sensitivity = float(detector.sensitivity)
    if detector.detector_type == AlertDetector.DetectorType.MARKET_SHOCK:
        return market_relevance_score(cluster) >= sensitivity
    if detector.detector_type == AlertDetector.DetectorType.ENTITY_BURST:
        return entity_importance_score(cluster) >= sensitivity
    if detector.detector_type == AlertDetector.DetectorType.SOURCE_BURST:
        return calculate_source_diversity(documents) >= sensitivity
    return calculate_trend_score(cluster) >= sensitivity


def _trigger_type(
    rule: AlertRule | None,
    detector: AlertDetector | None,
) -> str:
    if rule:
        return AlertHit.TriggerType.EXPLICIT_RULE_MATCH
    if detector and detector.detector_type == AlertDetector.DetectorType.MARKET_SHOCK:
        return AlertHit.TriggerType.MARKET_SHOCK
    if detector and detector.detector_type == AlertDetector.DetectorType.ENTITY_BURST:
        return AlertHit.TriggerType.ENTITY_BURST
    return AlertHit.TriggerType.AUTOMATIC_CLUSTER


def _alert_dedupe_key(
    cluster: EventCluster,
    rule: AlertRule | None,
    detector: AlertDetector | None,
) -> str:
    trigger = (
        f"rule:{rule.id}" if rule else f"detector:{detector.id if detector else 0}"
    )
    title = normalize_text(_cluster_title(cluster))
    day = cluster.first_seen_at.date().isoformat()
    return compute_content_hash(f"{trigger}:{day}:{title}")


def _matched_text(
    cluster: EventCluster,
    rule: AlertRule | None,
    detector: AlertDetector | None,
) -> str:
    if rule and rule.query:
        return rule.query
    if detector:
        return detector.detector_type
    return cluster.topic_label or cluster.label


def _cluster_search_text(
    cluster: EventCluster,
    documents: list[NormalizedDocument],
) -> str:
    bits = [
        cluster.label,
        cluster.canonical_title,
        cluster.summary,
        cluster.topic_label,
    ]
    bits.extend(str(keyword) for keyword in cluster.keywords)
    bits.extend(str(entity) for entity in cluster.entities)
    bits.extend(document.title for document in documents)
    return normalize_text(" ".join(bits))


def _cluster_title(cluster: EventCluster) -> str:
    return cluster.canonical_title or cluster.label or "Untitled event cluster"


def _reliability_score(documents: list[NormalizedDocument]) -> float:
    if not documents:
        return 0.5
    scores = [_document_reliability(document) for document in documents]
    return round(float(sum(scores) / len(scores)), 3)


def _document_reliability(document: NormalizedDocument) -> Decimal:
    source = document.source
    return max(source.reliability_score, source.reputation_score, Decimal("0.50"))


def _rule_or_detector_score(
    rule: AlertRule | None,
    detector: AlertDetector | None,
) -> float:
    if rule:
        return 1.0
    if detector:
        return max(0.5, float(detector.sensitivity))
    return 0.0


def _overlaps(configured_values: list[object], observed_values: set[str]) -> bool:
    wanted = {str(value).lower() for value in configured_values}
    return bool(wanted & observed_values)


def _update_document_hashes(document: NormalizedDocument) -> None:
    text = f"{document.title}\n{document.content or document.text}"
    document.content_hash = compute_content_hash(text)
    document.simhash = compute_simhash(text)
    document.text = document.content or document.text
    document.save(update_fields=["content_hash", "simhash", "text", "updated_at"])


def _upsert_exact_group(document: NormalizedDocument) -> DedupeGroup:
    group, _created = DedupeGroup.objects.update_or_create(
        group_type=DedupeGroup.GroupType.EXACT,
        content_hash=document.content_hash,
        defaults=_dedupe_defaults(document),
    )
    return group


def _dedupe_defaults(document: NormalizedDocument) -> dict[str, object]:
    count = NormalizedDocument.objects.filter(
        content_hash=document.content_hash
    ).count()
    return {
        "simhash": document.simhash,
        "representative_document": document,
        "document_count": count,
        "last_seen_at": timezone.now(),
    }


def _default_detector_specs() -> tuple[dict[str, object], ...]:
    return (
        _detector_spec("Emerging startup and VC trends", "emerging_topic", 0.45),
        _detector_spec("Entity burst monitor", "entity_burst", 0.40),
        _detector_spec("Source burst monitor", "source_burst", 0.50),
        _detector_spec("Market shock monitor", "market_shock", 0.35),
    )


def _detector_spec(
    name: str, detector_type: str, sensitivity: float
) -> dict[str, object]:
    return {
        "name": name,
        "detector_type": detector_type,
        "sensitivity": Decimal(str(sensitivity)),
        "config": {"offline": True, "baseline": "cluster_statistics"},
        "enabled": True,
    }


def _decimal(value: object) -> Decimal:
    return Decimal(str(round(float(value or 0), 2)))
