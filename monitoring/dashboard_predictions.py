"""Dashboard view models for recent high-risk source predictions."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

from monitoring.models import AlertHit, AlertRule, NormalizedDocument, Source

HIGH_RISK_SEVERITIES = (AlertRule.Severity.HIGH, AlertRule.Severity.CRITICAL)
FACTOR_LABELS = {
    "rule_match": "Rule match",
    "trend": "Trend",
    "novelty": "Novelty",
    "source_diversity": "Source diversity",
    "entity_importance": "Entity importance",
    "market_relevance": "Market relevance",
    "reliability": "Reliability",
}


@dataclass(frozen=True, slots=True)
class PredictionFactor:
    label: str
    score: float


@dataclass(frozen=True, slots=True)
class PredictionEvidenceDocument:
    title: str
    url: str


@dataclass(frozen=True, slots=True)
class SourcePredictionSummary:
    event_title: str
    source_name: str
    provider_name: str
    owner_name: str
    target: str
    probability_percent: int
    factors: list[PredictionFactor]
    evidence_documents: list[PredictionEvidenceDocument]
    detected_at: datetime


def list_recent_high_risk_predictions(limit: int = 5) -> list[SourcePredictionSummary]:
    """Return dashboard-ready high-risk prediction summaries.

    Example:
        `summaries = list_recent_high_risk_predictions(limit=3)`
    """
    alerts = AlertHit.objects.select_related(
        "cluster", "representative_document", "source", "document"
    )
    alerts = alerts.prefetch_related("alerthitdocument_set__document")
    alerts = alerts.filter(severity__in=HIGH_RISK_SEVERITIES)
    alerts = alerts.order_by("-detected_at", "-occurred_at")[:limit]
    return [_prediction_summary(alert) for alert in alerts]


def _prediction_summary(alert: AlertHit) -> SourcePredictionSummary:
    return SourcePredictionSummary(
        event_title=_event_title(alert),
        source_name=_source_name(alert),
        provider_name=_provider_name(alert),
        owner_name=_owner_name(alert),
        target=_target_name(alert),
        probability_percent=_probability_percent(alert),
        factors=_top_factors(alert),
        evidence_documents=_evidence_documents(alert),
        detected_at=alert.detected_at,
    )


def _event_title(alert: AlertHit) -> str:
    if alert.title:
        return alert.title
    if alert.cluster and alert.cluster.canonical_title:
        return alert.cluster.canonical_title
    return "Untitled source event"


def _source_name(alert: AlertHit) -> str:
    source = _alert_source(alert)
    if source:
        return source.name
    return "Unknown source"


def _provider_name(alert: AlertHit) -> str:
    provider = _metadata_choice(alert, ("provider", "provider_name", "source_provider"))
    if provider:
        return provider
    source = _alert_source(alert)
    return source.get_source_kind_display() if source else "Unknown provider"


def _owner_name(alert: AlertHit) -> str:
    owner = _metadata_choice(alert, ("owner", "owner_name", "source_owner"))
    if owner:
        return owner
    source = _alert_source(alert)
    if source and source.state_affiliation:
        return source.state_affiliation
    return "Unknown owner"


def _target_name(alert: AlertHit) -> str:
    target = _metadata_choice(alert, ("target", "target_name", "target_entity"))
    if target:
        return target
    entity = _first_text(alert.cluster.entities if alert.cluster else [])
    if entity:
        return entity
    return _document_target(alert)


def _document_target(alert: AlertHit) -> str:
    document = _representative_document(alert)
    entity = _first_text(document.entities if document else [])
    if entity:
        return entity
    source = _alert_source(alert)
    return source.get_category_display() if source else "Unspecified target"


def _probability_percent(alert: AlertHit) -> int:
    probability = _metadata_number(alert, ("probability", "probability_score"))
    score = probability if probability is not None else float(alert.severity_score)
    normalized_score = score / 100 if score > 1 else score
    bounded_score = min(max(normalized_score, 0.0), 1.0)
    return round(bounded_score * 100)


def _top_factors(alert: AlertHit) -> list[PredictionFactor]:
    factors = _breakdown_factors(alert)
    if not factors:
        factors = _stored_score_factors(alert)
    return sorted(factors, key=lambda factor: factor.score, reverse=True)[:3]


def _breakdown_factors(alert: AlertHit) -> list[PredictionFactor]:
    metadata = _metadata_mapping(alert.metadata)
    breakdown = _metadata_mapping(metadata.get("score_breakdown"))
    return [
        PredictionFactor(label, score)
        for key, label in FACTOR_LABELS.items()
        if (score := _number_value(breakdown.get(key))) is not None
    ]


def _stored_score_factors(alert: AlertHit) -> list[PredictionFactor]:
    return [
        PredictionFactor("Trend", float(alert.trend_score)),
        PredictionFactor("Novelty", float(alert.novelty_score)),
        PredictionFactor("Source diversity", float(alert.source_diversity_score)),
        PredictionFactor("Confidence", float(alert.confidence_score)),
        PredictionFactor("Market relevance", float(alert.market_relevance_score)),
    ]


def _evidence_documents(alert: AlertHit) -> list[PredictionEvidenceDocument]:
    documents = [
        edge.document
        for edge in alert.alerthitdocument_set.all()
        if edge.document_id and edge.document
    ]
    representative = _representative_document(alert)
    if not documents and representative:
        documents = [representative]
    return [
        PredictionEvidenceDocument(title=document.title, url=document.canonical_url)
        for document in documents[:3]
        if document
    ]


def _alert_source(alert: AlertHit) -> Source | None:
    if alert.source_id and alert.source:
        return alert.source
    document = _representative_document(alert)
    return document.source if document else None


def _representative_document(alert: AlertHit) -> NormalizedDocument | None:
    if alert.representative_document_id and alert.representative_document:
        return alert.representative_document
    if alert.document_id and alert.document:
        return alert.document
    return None


def _metadata_choice(alert: AlertHit, keys: tuple[str, ...]) -> str:
    for key in keys:
        value = _metadata_text(alert, key)
        if value:
            return value
    return ""


def _metadata_text(alert: AlertHit, key: str) -> str:
    for metadata in (_metadata_mapping(alert.metadata), _document_metadata(alert)):
        value = metadata.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


def _metadata_number(alert: AlertHit, keys: tuple[str, ...]) -> float | None:
    for key in keys:
        value = _number_value(_metadata_mapping(alert.metadata).get(key))
        if value is not None:
            return value
    return None


def _document_metadata(alert: AlertHit) -> dict[str, object]:
    document = _representative_document(alert)
    if not document:
        return {}
    return _metadata_mapping(document.metadata)


def _metadata_mapping(value: object) -> dict[str, object]:
    if not isinstance(value, dict):
        return {}
    return {str(key): item for key, item in value.items()}


def _first_text(values: object) -> str:
    if not isinstance(values, list):
        return ""
    for value in values:
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


def _number_value(value: object) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (Decimal, int, float)):
        return float(value)
    if not isinstance(value, str):
        return None
    return _string_number_value(value)


def _string_number_value(value: str) -> float | None:
    try:
        return float(value)
    except ValueError:
        return None
