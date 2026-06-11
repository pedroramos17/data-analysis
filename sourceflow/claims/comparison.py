"""Source-by-source claim comparison for event clusters."""

from __future__ import annotations

import re
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Iterable

from sourceflow.analysis.source_bias import (
    BiasFinding,
    CoverageSignal,
    SourceGroupKey,
    analyze_source_bias,
    source_group_key,
)
from sourceflow.events.clustering import EventCluster
from sourceflow.reasoning.contradictions import claim_key


@dataclass(frozen=True)
class SourceClaimSummary:
    """Claim coverage summary for one source group."""

    group_key: SourceGroupKey
    article_count: int
    claim_count: int
    claim_frequency: dict[str, int]
    polarity_counts: dict[str, int]
    entity_focus: dict[str, int]
    headline_terms: dict[str, int]
    evidence_diversity: int
    time_to_coverage_seconds: int | None
    omitted_claims: tuple[str, ...]
    reliability_score: Decimal


@dataclass(frozen=True)
class SourceClaimComparison:
    """Complete source comparison for one event cluster."""

    cluster_id: str
    group_by: tuple[str, ...]
    summaries: tuple[SourceClaimSummary, ...]
    findings: tuple[BiasFinding, ...]
    assumption_policy: str = "PartialCWA"

    @property
    def omissions(self) -> tuple[BiasFinding, ...]:
        return tuple(finding for finding in self.findings if finding.detection_type == "omission")


def compare_event_cluster_claims(
    cluster: EventCluster,
    *,
    claims: Iterable[object] | None = None,
    expected_sources: Iterable[object] = (),
    group_by: tuple[str, ...] = ("owner",),
) -> SourceClaimComparison:
    """Compare source-group coverage for a single event cluster."""
    claim_list = tuple(claims if claims is not None else cluster.claims)
    source_records = _sources_from_records((*cluster.events, *claim_list, *tuple(expected_sources)))
    groups = {source_group_key(source, fields=group_by): source for source in source_records}
    grouped_claims: dict[SourceGroupKey, list[object]] = defaultdict(list)
    grouped_docs: dict[SourceGroupKey, set[object]] = defaultdict(set)
    for claim in claim_list:
        key = source_group_key(_source(claim), fields=group_by)
        grouped_claims[key].append(claim)
        if _value(claim, "document_id"):
            grouped_docs[key].add(_value(claim, "document_id"))
    for event in cluster.events:
        key = source_group_key(_source(event), fields=group_by)
        if _value(event, "document_id"):
            grouped_docs[key].add(_value(event, "document_id"))
    all_claim_keys = {_claim_key_text(claim) for claim in claim_list}
    summaries: list[SourceClaimSummary] = []
    signals: list[CoverageSignal] = []
    for key in sorted(groups, key=lambda item: item.label(group_by)):
        group_claims = grouped_claims.get(key, [])
        claim_frequency = Counter(_claim_key_text(claim) for claim in group_claims)
        polarity_counts = Counter(str(_value(claim, "polarity") or "unknown") for claim in group_claims)
        entity_focus = Counter(_entity_label(_value(claim, "subject_entity")) or str(_value(claim, "subject_entity_id")) for claim in group_claims)
        headline_terms = Counter()
        for record in [*group_claims, *cluster.events]:
            if source_group_key(_source(record), fields=group_by) == key:
                headline_terms.update(_headline_terms(_document(record)))
        first_seen = _first_seen(group_claims, [event for event in cluster.events if source_group_key(_source(event), fields=group_by) == key])
        delay = _delay_seconds(cluster.first_seen_at, first_seen)
        source = groups[key]
        summary = SourceClaimSummary(
            group_key=key,
            article_count=len(grouped_docs.get(key, set())),
            claim_count=len(group_claims),
            claim_frequency=dict(claim_frequency),
            polarity_counts=dict(polarity_counts),
            entity_focus={k: v for k, v in dict(entity_focus).items() if k},
            headline_terms=dict(headline_terms),
            evidence_diversity=len({_value(claim, "evidence_span_id") for claim in group_claims if _value(claim, "evidence_span_id")}),
            time_to_coverage_seconds=delay,
            omitted_claims=tuple(sorted(all_claim_keys - set(claim_frequency))),
            reliability_score=Decimal(str(_value(source, "reliability_score") or 0)),
        )
        summaries.append(summary)
        signals.append(
            CoverageSignal(
                group_key=key,
                article_count=summary.article_count,
                claim_count=summary.claim_count,
                claim_frequency=summary.claim_frequency,
                polarity_counts=summary.polarity_counts,
                entity_focus=summary.entity_focus,
                headline_terms=summary.headline_terms,
                evidence_diversity=summary.evidence_diversity,
                time_to_coverage_seconds=summary.time_to_coverage_seconds,
                reliability_score=summary.reliability_score,
            )
        )
    return SourceClaimComparison(
        cluster_id=cluster.cluster_id,
        group_by=group_by,
        summaries=tuple(summaries),
        findings=tuple(analyze_source_bias(signals)),
    )


def _claim_key_text(claim: object) -> str:
    key = claim_key(claim)
    return f"{key.subject_id}:{key.predicate}:{key.object_key}"


def _sources_from_records(records: Iterable[object]) -> list[object]:
    seen: set[str] = set()
    sources: list[object] = []
    for record in records:
        source = record if _looks_like_source(record) else _source(record)
        source_id = str(_value(source, "pk") or _value(source, "id") or _value(source, "name"))
        if source and source_id not in seen:
            seen.add(source_id)
            sources.append(source)
    return sources


def _looks_like_source(record: object) -> bool:
    return bool(_value(record, "source_type") or _value(record, "provider_owner") or _value(record, "bias_tags"))


def _source(record: object) -> object:
    return _value(record, "source") or {"id": _value(record, "source_id"), "name": str(_value(record, "source_id"))}


def _document(record: object) -> object:
    return _value(record, "document") or {}


def _headline_terms(document: object) -> list[str]:
    title = str(_value(document, "title") or "")
    stopwords = {"a", "an", "and", "for", "in", "of", "on", "the", "to"}
    return [token for token in re.findall(r"[a-z0-9]+", title.lower()) if token not in stopwords]


def _first_seen(claims: list[object], events: list[object]) -> datetime | None:
    values = []
    for record in [*claims, *events]:
        document = _document(record)
        seen = _value(document, "published_at") or _value(record, "event_time") or _value(record, "created_at")
        if seen:
            values.append(seen)
    return min(values) if values else None


def _delay_seconds(cluster_first: datetime | None, group_first: datetime | None) -> int | None:
    if cluster_first is None or group_first is None:
        return None
    return int((group_first - cluster_first).total_seconds())


def _entity_label(entity: object) -> str:
    return str(_value(entity, "canonical_name") or _value(entity, "name") or "") if entity else ""


def _value(record: object, key: str) -> object:
    return record.get(key, "") if isinstance(record, dict) else getattr(record, key, "")
