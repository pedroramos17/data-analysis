"""Neutral event coverage comparison service."""

import json
from collections import Counter, defaultdict
from datetime import datetime
from statistics import median

from django.utils import timezone

from monitoring.models import (
    Claim,
    ClaimCluster,
    ClaimClusterMember,
    DocumentTopic,
    EventComparisonSnapshot,
    EventCoverage,
    NormalizedDocument,
    TopicCluster,
)
from monitoring.services.deduplication import content_hash
from monitoring.services.entities import dominant_entity_names
from monitoring.services.framing import article_frame_features


def compare_event_coverage(
    event: TopicCluster,
    omission_threshold: float = 0.60,
) -> EventComparisonSnapshot:
    """Compute and persist a neutral comparison snapshot for one event.

    Example:
        `snapshot = compare_event_coverage(event)`
    """
    articles = _event_articles(event)
    claim_groups = _claim_groups(event, articles)
    provider_articles = _provider_articles(articles)
    payload = _comparison_payload(provider_articles, claim_groups, omission_threshold)
    _replace_claim_clusters(event, claim_groups)
    _replace_coverage_rows(event, articles, provider_articles, payload)
    return _create_snapshot(event, payload)


def _event_articles(event: TopicCluster) -> list[NormalizedDocument]:
    links = DocumentTopic.objects.filter(cluster=event, is_incorrect=False)
    return [
        link.document for link in links.select_related("document__source__provider")
    ]


def _claim_groups(
    event: TopicCluster,
    articles: list[NormalizedDocument],
) -> dict[str, list[Claim]]:
    claims = Claim.objects.filter(article__in=articles).select_related(
        "article__source__provider"
    )
    grouped: dict[str, list[Claim]] = defaultdict(list)
    for claim in claims:
        grouped[claim.normalized_claim].append(claim)
    return dict(grouped)


def _provider_articles(
    articles: list[NormalizedDocument],
) -> dict[str, list[NormalizedDocument]]:
    grouped: dict[str, list[NormalizedDocument]] = defaultdict(list)
    for article in articles:
        grouped[article.source.provider.name].append(article)
    return dict(grouped)


def _comparison_payload(
    provider_articles: dict[str, list[NormalizedDocument]],
    claim_groups: dict[str, list[Claim]],
    omission_threshold: float,
) -> dict[str, object]:
    shared_claims = _shared_claims(claim_groups)
    unique_claims = _unique_claims_by_provider(claim_groups)
    return {
        "coverage": _coverage_payload(provider_articles),
        "claims": {
            "shared": shared_claims,
            "unique_by_provider": unique_claims,
        },
        "omissions": {
            "claims": _claim_omissions(
                provider_articles, claim_groups, omission_threshold
            ),
            "entities": _entity_omissions(provider_articles, omission_threshold),
        },
        "framing": _framing_differences(provider_articles),
        "amplification": _provider_amplification(provider_articles),
    }


def _coverage_payload(
    provider_articles: dict[str, list[NormalizedDocument]],
) -> dict[str, object]:
    providers = {}
    for provider_name, articles in provider_articles.items():
        providers[provider_name] = _coverage_entry(articles)
    return {"providers": providers}


def _coverage_entry(articles: list[NormalizedDocument]) -> dict[str, object]:
    dates = [_article_time(article) for article in articles]
    return {
        "article_count": len(articles),
        "first_seen_at": min(dates).isoformat() if dates else "",
        "last_seen_at": max(dates).isoformat() if dates else "",
        "dominant_entities": dominant_entity_names(articles),
    }


def _shared_claims(claim_groups: dict[str, list[Claim]]) -> list[str]:
    return [
        claims[0].claim_text
        for claims in claim_groups.values()
        if len(_claim_provider_names(claims)) > 1
    ]


def _unique_claims_by_provider(
    claim_groups: dict[str, list[Claim]],
) -> dict[str, list[str]]:
    unique_claims: dict[str, list[str]] = defaultdict(list)
    for claims in claim_groups.values():
        providers = _claim_provider_names(claims)
        if len(providers) == 1:
            unique_claims[next(iter(providers))].append(claims[0].claim_text)
    return dict(unique_claims)


def _claim_omissions(
    provider_articles: dict[str, list[NormalizedDocument]],
    claim_groups: dict[str, list[Claim]],
    omission_threshold: float,
) -> list[str]:
    provider_names = set(provider_articles)
    messages = []
    for claims in claim_groups.values():
        messages.extend(
            _claim_omission_messages(provider_names, claims, omission_threshold)
        )
    return messages


def _claim_omission_messages(
    provider_names: set[str],
    claims: list[Claim],
    omission_threshold: float,
) -> list[str]:
    claim_providers = _claim_provider_names(claims)
    ratio = len(claim_providers) / max(1, len(provider_names))
    if ratio < omission_threshold:
        return []
    percent = round(ratio * 100)
    return [
        _omission_sentence(provider, claims[0].claim_text, percent)
        for provider in provider_names - claim_providers
    ]


def _entity_omissions(
    provider_articles: dict[str, list[NormalizedDocument]],
    omission_threshold: float,
) -> list[str]:
    entity_providers = _entity_provider_map(provider_articles)
    provider_names = set(provider_articles)
    messages = []
    for entity, providers in entity_providers.items():
        ratio = len(providers) / max(1, len(provider_names))
        if ratio >= omission_threshold:
            messages.extend(
                _entity_omission_messages(provider_names, providers, entity, ratio)
            )
    return messages


def _entity_provider_map(
    provider_articles: dict[str, list[NormalizedDocument]],
) -> dict[str, set[str]]:
    entity_providers: dict[str, set[str]] = defaultdict(set)
    for provider, articles in provider_articles.items():
        for entity in dominant_entity_names(articles):
            entity_providers[entity].add(provider)
    return dict(entity_providers)


def _entity_omission_messages(
    provider_names: set[str],
    providers: set[str],
    entity: str,
    ratio: float,
) -> list[str]:
    percent = round(ratio * 100)
    return [
        f"Provider {provider} covered the event but did not mention entity "
        f"{entity!r}, which appeared in {percent}% of comparable coverage."
        for provider in provider_names - providers
    ]


def _framing_differences(
    provider_articles: dict[str, list[NormalizedDocument]],
) -> dict[str, dict[str, float]]:
    return {
        provider: _average_frame_features(articles)
        for provider, articles in provider_articles.items()
    }


def _average_frame_features(articles: list[NormalizedDocument]) -> dict[str, float]:
    totals: Counter[str] = Counter()
    for article in articles:
        totals.update(article_frame_features(article))
    if not articles:
        return {}
    return {key: round(value / len(articles), 4) for key, value in totals.items()}


def _provider_amplification(
    provider_articles: dict[str, list[NormalizedDocument]],
) -> dict[str, dict[str, float]]:
    counts = [len(articles) for articles in provider_articles.values()]
    baseline = median(counts) if counts else 1
    return {
        provider: {"score": round(len(articles) / max(1, baseline), 4)}
        for provider, articles in provider_articles.items()
    }


def _replace_claim_clusters(
    event: TopicCluster,
    claim_groups: dict[str, list[Claim]],
) -> None:
    ClaimCluster.objects.filter(event=event).delete()
    for normalized_claim, claims in claim_groups.items():
        claim_cluster = _create_claim_cluster(event, normalized_claim, claims)
        _create_claim_members(claim_cluster, claims)


def _create_claim_cluster(
    event: TopicCluster,
    normalized_claim: str,
    claims: list[Claim],
) -> ClaimCluster:
    return ClaimCluster.objects.create(
        event=event,
        normalized_claim=normalized_claim,
        representative_claim=claims[0].claim_text,
        provider_count=len(_claim_provider_names(claims)),
        article_count=len({claim.article_id for claim in claims}),
    )


def _create_claim_members(claim_cluster: ClaimCluster, claims: list[Claim]) -> None:
    for claim in claims:
        ClaimClusterMember.objects.create(claim_cluster=claim_cluster, claim=claim)


def _replace_coverage_rows(
    event: TopicCluster,
    articles: list[NormalizedDocument],
    provider_articles: dict[str, list[NormalizedDocument]],
    payload: dict[str, object],
) -> None:
    EventCoverage.objects.filter(event=event).delete()
    _create_source_coverage(event, articles)
    _create_provider_coverage(event, provider_articles, payload)
    _create_owner_coverage(event, articles)


def _create_source_coverage(
    event: TopicCluster, articles: list[NormalizedDocument]
) -> None:
    for article in articles:
        EventCoverage.objects.create(
            event=event,
            coverage_type="source",
            source=article.source,
            article_count=1,
            first_seen_at=_article_time(article),
            last_seen_at=_article_time(article),
        )


def _create_provider_coverage(
    event: TopicCluster,
    provider_articles: dict[str, list[NormalizedDocument]],
    payload: dict[str, object],
) -> None:
    amplification = payload["amplification"]
    for articles in provider_articles.values():
        provider = articles[0].source.provider
        EventCoverage.objects.create(
            event=event,
            coverage_type="provider",
            provider=provider,
            article_count=len(articles),
            amplification_score=amplification[provider.name]["score"],
        )


def _create_owner_coverage(
    event: TopicCluster, articles: list[NormalizedDocument]
) -> None:
    owner_articles: dict[int, list[NormalizedDocument]] = defaultdict(list)
    for article in articles:
        owner = article.source.provider.owner
        if owner:
            owner_articles[owner.id].append(article)
    for grouped_articles in owner_articles.values():
        _create_one_owner_coverage(event, grouped_articles)


def _create_one_owner_coverage(
    event: TopicCluster,
    articles: list[NormalizedDocument],
) -> None:
    EventCoverage.objects.create(
        event=event,
        coverage_type="owner",
        owner=articles[0].source.provider.owner,
        article_count=len(articles),
    )


def _create_snapshot(
    event: TopicCluster,
    payload: dict[str, object],
) -> EventComparisonSnapshot:
    encoded = json.dumps(payload, sort_keys=True, default=str)
    return EventComparisonSnapshot.objects.create(
        event=event,
        payload=payload,
        generated_at=timezone.now(),
        snapshot_hash=content_hash(encoded),
    )


def _claim_provider_names(claims: list[Claim]) -> set[str]:
    return {claim.article.source.provider.name for claim in claims}


def _omission_sentence(provider: str, claim_text: str, percent: int) -> str:
    return (
        f"Provider {provider} covered the event but did not mention claim "
        f"{claim_text!r}, which appeared in {percent}% of comparable coverage."
    )


def _article_time(article: NormalizedDocument) -> datetime:
    return article.published_at or article.fetched_at or article.created_at
