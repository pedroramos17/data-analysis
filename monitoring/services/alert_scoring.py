"""Pure scoring functions for the offline alert engine."""

from __future__ import annotations

import hashlib
import re
from collections import Counter
from dataclasses import dataclass

from django.utils import timezone

from monitoring.models import AlertDetector, AlertRule, EventCluster, NormalizedDocument

TOKEN_PATTERN = re.compile(r"[a-z0-9][a-z0-9_.-]{1,}")
MARKET_TERMS = {
    "ai",
    "funding",
    "ipo",
    "market",
    "revenue",
    "startup",
    "valuation",
    "venture",
    "vc",
}


@dataclass(frozen=True, slots=True)
class AlertScoreBreakdown:
    """Component scores used to explain an alert."""

    rule_match: float
    trend: float
    novelty: float
    source_diversity: float
    entity_importance: float
    market_relevance: float
    reliability: float


def normalize_text(text: str) -> str:
    """Normalize text before dedupe and scoring."""
    lowered = text.lower().strip()
    return " ".join(lowered.split())


def compute_content_hash(text: str) -> str:
    """Compute stable SHA-256 over normalized text."""
    normalized = normalize_text(text)
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def compute_simhash(text: str) -> str:
    """Compute a cheap stable near-dedupe hash."""
    tokens = TOKEN_PATTERN.findall(normalize_text(text))
    if not tokens:
        return compute_content_hash(text)[:16]
    top_tokens = sorted(token for token, _count in Counter(tokens).most_common(16))
    return hashlib.sha256(" ".join(top_tokens).encode("utf-8")).hexdigest()[:16]


def calculate_source_diversity(documents: list[NormalizedDocument]) -> float:
    """Score diversity from unique sources in an evidence set."""
    if not documents:
        return 0.0
    source_ids = {document.source_id for document in documents}
    return round(min(1.0, len(source_ids) / 5), 3)


def calculate_novelty_score(cluster: EventCluster) -> float:
    """Score cluster novelty from first-seen recency."""
    age_hours = max(
        0.0, (timezone.now() - cluster.first_seen_at).total_seconds() / 3600
    )
    return round(max(0.1, 1.0 - min(1.0, age_hours / 168)), 3)


def calculate_trend_score(cluster: EventCluster) -> float:
    """Score trend from document count, source count, and cluster score."""
    document_score = min(1.0, cluster.document_count / 10)
    source_score = min(1.0, cluster.source_count / 5)
    existing_score = float(cluster.score or 0)
    stored_trend = float(cluster.trend_score or 0)
    return round(max(document_score, source_score, existing_score, stored_trend), 3)


def calculate_alert_score(breakdown: AlertScoreBreakdown) -> float:
    """Compute the MVP weighted alert score."""
    return round(
        0.20 * breakdown.rule_match
        + 0.20 * breakdown.trend
        + 0.15 * breakdown.novelty
        + 0.15 * breakdown.source_diversity
        + 0.10 * breakdown.entity_importance
        + 0.10 * breakdown.market_relevance
        + 0.10 * breakdown.reliability,
        3,
    )


def map_score_to_severity(score: float) -> str:
    """Map numeric alert score to severity label."""
    if score >= 0.85:
        return AlertRule.Severity.CRITICAL
    if score >= 0.70:
        return AlertRule.Severity.HIGH
    if score >= 0.50:
        return AlertRule.Severity.MEDIUM
    return AlertRule.Severity.LOW


def build_alert_explanation(
    cluster: EventCluster,
    rule: AlertRule | None = None,
    detector: AlertDetector | None = None,
    score_breakdown: AlertScoreBreakdown | None = None,
) -> str:
    """Build a human-readable reason for an alert."""
    trigger = rule.name if rule else detector.name if detector else "alert engine"
    parts = [f"Triggered by {trigger} on cluster '{_cluster_title(cluster)}'."]
    parts.append(f"Evidence spans {cluster.document_count} documents.")
    if score_breakdown:
        parts.append(_breakdown_sentence(score_breakdown))
    return " ".join(parts)


def market_relevance_score(cluster: EventCluster) -> float:
    """Score startup, VC, and market relevance from cluster text."""
    text = normalize_text(
        " ".join([cluster.label, cluster.summary, cluster.topic_label])
    )
    tokens = set(TOKEN_PATTERN.findall(text))
    return round(min(1.0, len(tokens & MARKET_TERMS) / 3), 3)


def entity_importance_score(cluster: EventCluster) -> float:
    """Score simple entity density in a cluster."""
    entity_count = len(cluster.entities or [])
    return round(min(1.0, entity_count / 5), 3)


def _cluster_title(cluster: EventCluster) -> str:
    return cluster.canonical_title or cluster.label or "Untitled event cluster"


def _breakdown_sentence(breakdown: AlertScoreBreakdown) -> str:
    return (
        "Scores:"
        f" trend={breakdown.trend:.2f}, novelty={breakdown.novelty:.2f},"
        f" diversity={breakdown.source_diversity:.2f},"
        f" market={breakdown.market_relevance:.2f}."
    )
