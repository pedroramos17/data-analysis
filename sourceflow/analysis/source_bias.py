"""Source grouping, reliability metadata, and coverage-bias signals."""

from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Iterable, Mapping


@dataclass(frozen=True)
class SourceGroupKey:
    """Provider grouping key for comparing source coverage."""

    owner: str = "unknown_owner"
    provider: str = "unknown_provider"
    region: str = "unknown_region"
    category: str = "uncategorized"
    content_type: str = "other"

    def label(self, fields: tuple[str, ...] = ("owner",)) -> str:
        return " | ".join(getattr(self, field) for field in fields)


@dataclass(frozen=True)
class SourceReliabilityMetadata:
    """Reliability and categorical metadata attached to a source."""

    source_id: str
    reliability_score: Decimal
    bias_tags: tuple[str, ...]
    region: str
    content_type: str
    owner: str


@dataclass(frozen=True)
class SourceGroup:
    """One group of sources sharing owner/provider/region/category/type."""

    key: SourceGroupKey
    sources: tuple[object, ...]
    reliability_score: Decimal
    source_ids: tuple[str, ...]
    source_names: tuple[str, ...]


@dataclass(frozen=True)
class CoverageSignal:
    """Signals used to compare one source group against a cluster."""

    group_key: SourceGroupKey
    article_count: int = 0
    claim_count: int = 0
    claim_frequency: Mapping[str, int] = field(default_factory=dict)
    polarity_counts: Mapping[str, int] = field(default_factory=dict)
    entity_focus: Mapping[str, int] = field(default_factory=dict)
    headline_terms: Mapping[str, int] = field(default_factory=dict)
    evidence_diversity: int = 0
    time_to_coverage_seconds: int | None = None
    reliability_score: Decimal = Decimal("0")


@dataclass(frozen=True)
class BiasFinding:
    """One source comparison finding."""

    detection_type: str
    group_key: SourceGroupKey
    description: str
    severity: Decimal
    evidence: Mapping[str, object]
    assumption_policy: str = "PartialCWA"
    inferred_false: bool = False


def source_group_key(source: object, *, fields: tuple[str, ...] | None = None) -> SourceGroupKey:
    """Return the normalized grouping key for a source or mapping."""
    owner = _owner_name(source)
    provider = _text(_value(source, "name"), "unknown_provider")
    region = _text(_value(source, "country"), "unknown_region")
    tags = _bias_tags(source)
    category = tags[0] if tags else "uncategorized"
    content_type = _text(_value(source, "source_type"), "other")
    key = SourceGroupKey(owner=owner, provider=provider, region=region, category=category, content_type=content_type)
    if not fields:
        return key
    values = {field: getattr(key, field) if field in fields else "*" for field in key.__dataclass_fields__}
    return SourceGroupKey(**values)


def group_sources(
    sources: Iterable[object],
    *,
    by: tuple[str, ...] = ("owner",),
) -> list[SourceGroup]:
    """Group sources by owner/provider/region/category/content type."""
    grouped: dict[SourceGroupKey, list[object]] = defaultdict(list)
    for source in sources:
        grouped[source_group_key(source, fields=by)].append(source)
    groups: list[SourceGroup] = []
    for key, members in grouped.items():
        scores = [Decimal(str(_value(source, "reliability_score") or 0)) for source in members]
        groups.append(
            SourceGroup(
                key=key,
                sources=tuple(members),
                reliability_score=(sum(scores, Decimal("0")) / len(scores)).quantize(Decimal("0.01")) if scores else Decimal("0"),
                source_ids=tuple(str(_value(source, "pk") or _value(source, "id")) for source in members),
                source_names=tuple(str(_value(source, "name")) for source in members),
            )
        )
    return sorted(groups, key=lambda group: group.key.label(by))


def source_reliability_metadata(source: object) -> SourceReliabilityMetadata:
    """Return current reliability metadata for a source."""
    return SourceReliabilityMetadata(
        source_id=str(_value(source, "pk") or _value(source, "id")),
        reliability_score=Decimal(str(_value(source, "reliability_score") or 0)),
        bias_tags=_bias_tags(source),
        region=_text(_value(source, "country"), "unknown_region"),
        content_type=_text(_value(source, "source_type"), "other"),
        owner=_owner_name(source),
    )


def update_source_reliability_metadata(
    source: object,
    *,
    reliability_score: Decimal | str | float | None = None,
    bias_tags: Iterable[str] | None = None,
    country: str | None = None,
    source_type: str | None = None,
) -> SourceReliabilityMetadata:
    """Update source reliability metadata on a Django Source instance."""
    update_fields: list[str] = []
    if reliability_score is not None:
        source.reliability_score = Decimal(str(reliability_score))
        update_fields.append("reliability_score")
    if bias_tags is not None:
        source.bias_tags = [_normalize_tag(tag) for tag in bias_tags]
        update_fields.append("bias_tags")
    if country is not None:
        source.country = country
        update_fields.append("country")
    if source_type is not None:
        source.source_type = source_type
        update_fields.append("source_type")
    if update_fields and hasattr(source, "save"):
        source.save(update_fields=[*update_fields, "updated_at"])
    return source_reliability_metadata(source)


def analyze_source_bias(signals: Iterable[CoverageSignal]) -> list[BiasFinding]:
    """Detect omission, framing, amplification, and contradiction findings."""
    signal_list = list(signals)
    if not signal_list:
        return []
    findings: list[BiasFinding] = []
    all_claims = set().union(*(set(signal.claim_frequency) for signal in signal_list))
    average_articles = Decimal(sum(signal.article_count for signal in signal_list)) / len(signal_list)
    average_claims = Decimal(sum(signal.claim_count for signal in signal_list)) / len(signal_list)
    global_polarity = Counter()
    for signal in signal_list:
        global_polarity.update(signal.polarity_counts)
    dominant_polarity = global_polarity.most_common(1)[0][0] if global_polarity else ""

    for signal in signal_list:
        missing_claims = sorted(all_claims - set(signal.claim_frequency))
        for claim_key in missing_claims:
            findings.append(
                BiasFinding(
                    detection_type="omission",
                    group_key=signal.group_key,
                    description=f"source omitted {claim_key}",
                    severity=Decimal("0.50"),
                    evidence={"claim_key": claim_key},
                )
            )
        if average_articles and Decimal(signal.article_count) > average_articles * Decimal("1.5"):
            findings.append(_finding("overemphasis", signal, "source published unusually high article volume", {"article_count": signal.article_count}))
        if average_claims and 0 < Decimal(signal.claim_count) < average_claims * Decimal("0.5"):
            findings.append(_finding("underemphasis", signal, "source published unusually low claim volume", {"claim_count": signal.claim_count}))
        repeated = {key: count for key, count in signal.claim_frequency.items() if count > 1}
        if repeated:
            findings.append(_finding("claim_repetition", signal, "source repeated one or more claims", {"repeated_claims": repeated}))
        if signal.article_count > 1 and signal.claim_count >= average_claims * Decimal("1.5"):
            findings.append(_finding("provider_amplification", signal, "provider group amplified cluster coverage", {"article_count": signal.article_count, "claim_count": signal.claim_count}))
        if dominant_polarity and signal.polarity_counts and dominant_polarity not in signal.polarity_counts:
            findings.append(_finding("sentiment_shift", signal, "source polarity differs from cluster majority", {"cluster_polarity": dominant_polarity, "source_polarity": dict(signal.polarity_counts)}))
        if signal.headline_terms and _framing_is_shifted(signal, signal_list):
            findings.append(_finding("framing_shift", signal, "source headline framing differs from other groups", {"headline_terms": dict(signal.headline_terms)}))
        if _has_counterclaim_gap(signal, signal_list):
            findings.append(_finding("missing_counterclaim", signal, "source omitted counterclaim carried by another group", {"polarity_counts": dict(signal.polarity_counts)}))
        if _has_group_contradiction(signal):
            findings.append(_finding("claim_contradiction", signal, "source group contains contradictory claim polarities", {"polarity_counts": dict(signal.polarity_counts)}))
    return findings


def _finding(detection_type: str, signal: CoverageSignal, description: str, evidence: Mapping[str, object]) -> BiasFinding:
    return BiasFinding(
        detection_type=detection_type,
        group_key=signal.group_key,
        description=description,
        severity=Decimal("0.40"),
        evidence=evidence,
    )


def _framing_is_shifted(signal: CoverageSignal, signals: list[CoverageSignal]) -> bool:
    other_terms = Counter()
    for other in signals:
        if other.group_key != signal.group_key:
            other_terms.update(other.headline_terms)
    if not other_terms:
        return False
    source_top = {term for term, _count in Counter(signal.headline_terms).most_common(3)}
    other_top = {term for term, _count in other_terms.most_common(3)}
    return bool(source_top and other_top and source_top.isdisjoint(other_top))


def _has_counterclaim_gap(signal: CoverageSignal, signals: list[CoverageSignal]) -> bool:
    source_polarities = set(signal.polarity_counts)
    if not source_polarities:
        return False
    other_polarities = set()
    for other in signals:
        if other.group_key != signal.group_key:
            other_polarities.update(other.polarity_counts)
    return ("positive" in source_polarities and "negative" in other_polarities) or (
        "negative" in source_polarities and "positive" in other_polarities
    )


def _has_group_contradiction(signal: CoverageSignal) -> bool:
    return "positive" in signal.polarity_counts and "negative" in signal.polarity_counts


def _owner_name(source: object) -> str:
    owner = _value(source, "provider_owner")
    if owner:
        return _text(_value(owner, "canonical_name") or _value(owner, "name"), "unknown_owner")
    return _text(_value(source, "owner") or _value(source, "provider_owner_name") or _value(source, "name"), "unknown_owner")


def _bias_tags(source: object) -> tuple[str, ...]:
    tags = _value(source, "bias_tags") or ()
    return tuple(_normalize_tag(tag) for tag in tags if str(tag).strip())


def _normalize_tag(value: object) -> str:
    return "_".join(str(value).strip().lower().replace("-", "_").split())


def _text(value: object, fallback: str) -> str:
    normalized = _normalize_tag(value)
    return normalized or fallback


def _value(record: object, key: str) -> object:
    return record.get(key, "") if isinstance(record, Mapping) else getattr(record, key, "")
