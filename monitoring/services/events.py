"""Deterministic event clustering for article comparison."""

from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal

from django.db.models import QuerySet
from django.utils import timezone

from monitoring.models import DocumentTopic, NormalizedDocument, TopicCluster
from monitoring.services.embeddings import (
    article_vector,
    cosine_similarity,
    embed_article,
)
from monitoring.services.entities import (
    article_entity_names,
    dominant_entity_names,
    enrich_article_entities,
)


@dataclass(frozen=True, slots=True)
class EventClusteringSummary:
    """Counts produced by event clustering."""

    created_clusters: int
    linked_articles: int


@dataclass(frozen=True, slots=True)
class EventScore:
    """Explainable score components for one article-event link."""

    total: float
    embedding_score: float
    entity_score: float
    title_score: float
    used_embedding: bool


def cluster_articles_into_events(
    window_hours: int = 72,
    min_link_score: float = 0.50,
    merge_score: float = 0.85,
) -> EventClusteringSummary:
    """Cluster recent articles into event-capable topic clusters.

    Example:
        `summary = cluster_articles_into_events(window_hours=24)`
    """
    window_end = timezone.now()
    documents = _candidate_articles(
        window_end - timedelta(hours=window_hours), window_end
    )
    created_clusters = 0
    linked_articles = 0
    for article in documents:
        created, linked = _cluster_article(article, window_hours, min_link_score)
        created_clusters += int(created)
        linked_articles += int(linked)
    _merge_event_clusters(merge_score)
    return EventClusteringSummary(created_clusters, linked_articles)


def score_article_for_event(
    article: NormalizedDocument, event: TopicCluster
) -> EventScore:
    """Score one article against an existing event cluster.

    Example:
        `score_article_for_event(article, event)`
    """
    event_articles = _event_articles(event)
    if not event_articles:
        return EventScore(0.0, 0.0, 0.0, 0.0, False)
    scores = [
        _score_article_pair(article, event_article) for event_article in event_articles
    ]
    return max(scores, key=lambda score: score.total)


def _candidate_articles(
    window_start: datetime,
    window_end: datetime,
) -> QuerySet[NormalizedDocument]:
    return NormalizedDocument.objects.filter(
        created_at__gte=window_start,
        created_at__lte=window_end,
    ).select_related("source", "source__provider")


def _cluster_article(
    article: NormalizedDocument,
    window_hours: int,
    min_link_score: float,
) -> tuple[bool, bool]:
    if DocumentTopic.objects.filter(document=article, is_incorrect=False).exists():
        return False, False
    _prepare_article(article)
    event, score = _best_event_for_article(article, window_hours)
    if event is None or score.total < min_link_score:
        event = _create_micro_cluster(article)
        score = EventScore(1.0, 0.0, 1.0, 1.0, False)
        _link_article_to_event(article, event, score, min_link_score)
        return True, True
    _link_article_to_event(article, event, score, min_link_score)
    return False, True


def _prepare_article(article: NormalizedDocument) -> None:
    enrich_article_entities(article)
    embed_article(article)


def _best_event_for_article(
    article: NormalizedDocument,
    window_hours: int,
) -> tuple[TopicCluster | None, EventScore]:
    events = _candidate_events(article, window_hours)
    scored = [(event, score_article_for_event(article, event)) for event in events]
    if not scored:
        return None, EventScore(0.0, 0.0, 0.0, 0.0, False)
    return max(scored, key=lambda item: item[1].total)


def _candidate_events(
    article: NormalizedDocument,
    window_hours: int,
) -> QuerySet[TopicCluster]:
    published_at = _article_time(article)
    return TopicCluster.objects.filter(
        status=TopicCluster.Status.ACTIVE,
        merged_into__isnull=True,
        window_start__lte=published_at + timedelta(hours=window_hours),
        window_end__gte=published_at - timedelta(hours=window_hours),
    )


def _create_micro_cluster(article: NormalizedDocument) -> TopicCluster:
    published_at = _article_time(article)
    return TopicCluster.objects.create(
        label=_event_label(article),
        canonical_title=article.title,
        summary=(article.extracted_text or article.text or article.content)[:700],
        topic_label=_event_label(article),
        window_start=published_at - timedelta(hours=1),
        window_end=published_at + timedelta(hours=1),
        first_seen_at=published_at,
        last_seen_at=published_at,
        representative_document=article,
    )


def _link_article_to_event(
    article: NormalizedDocument,
    event: TopicCluster,
    score: EventScore,
    min_link_score: float,
) -> None:
    DocumentTopic.objects.create(
        cluster=event,
        document=article,
        similarity=_decimal(score.total),
        overlap_score=_decimal(max(score.entity_score, score.title_score)),
        role=_link_role(event),
        link_reason=_link_reason(score, min_link_score),
    )
    _refresh_event_counts(event)
    _mark_article_clustered(article)


def _score_article_pair(
    article: NormalizedDocument,
    event_article: NormalizedDocument,
) -> EventScore:
    embedding_score = cosine_similarity(
        article_vector(article), article_vector(event_article)
    )
    entity_score = _entity_overlap(article, event_article)
    title_score = _title_similarity(article.title, event_article.title)
    used_embedding = embedding_score > 0
    total = _weighted_score(embedding_score, entity_score, title_score, used_embedding)
    return EventScore(total, embedding_score, entity_score, title_score, used_embedding)


def _weighted_score(
    embedding_score: float,
    entity_score: float,
    title_score: float,
    used_embedding: bool,
) -> float:
    if used_embedding:
        total = 0.45 * embedding_score + 0.35 * entity_score + 0.20 * title_score
        return round(total, 4)
    return round(0.55 * entity_score + 0.45 * title_score, 4)


def _entity_overlap(first: NormalizedDocument, second: NormalizedDocument) -> float:
    first_names = article_entity_names(first)
    second_names = article_entity_names(second)
    if not first_names or not second_names:
        return 0.0
    return round(len(first_names & second_names) / len(first_names | second_names), 4)


def _title_similarity(first_title: str, second_title: str) -> float:
    first_tokens = _title_tokens(first_title)
    second_tokens = _title_tokens(second_title)
    if not first_tokens or not second_tokens:
        return 0.0
    return round(
        len(first_tokens & second_tokens) / len(first_tokens | second_tokens), 4
    )


def _title_tokens(title: str) -> set[str]:
    return {token for token in title.lower().split() if len(token) > 2}


def _event_articles(event: TopicCluster) -> list[NormalizedDocument]:
    links = DocumentTopic.objects.filter(cluster=event, is_incorrect=False)
    return [link.document for link in links.select_related("document")]


def _refresh_event_counts(event: TopicCluster) -> None:
    articles = _event_articles(event)
    event.document_count = len(articles)
    event.source_count = len({article.source_id for article in articles})
    event.entities = dominant_entity_names(articles)
    event.last_seen_at = max(
        (_article_time(article) for article in articles), default=event.last_seen_at
    )
    event.save(
        update_fields=["document_count", "source_count", "entities", "last_seen_at"]
    )


def _merge_event_clusters(merge_score: float) -> None:
    events = list(TopicCluster.objects.filter(status=TopicCluster.Status.ACTIVE))
    for index, event in enumerate(events):
        for candidate in events[index + 1 :]:
            _merge_pair_when_needed(event, candidate, merge_score)


def _merge_pair_when_needed(
    event: TopicCluster,
    candidate: TopicCluster,
    merge_score: float,
) -> None:
    score = _event_merge_score(event, candidate)
    if score < merge_score or candidate.merged_into_id:
        return
    DocumentTopic.objects.filter(cluster=candidate).update(cluster=event)
    candidate.status = TopicCluster.Status.MERGED
    candidate.merged_into = event
    candidate.merge_reason = {"score": score, "threshold": merge_score}
    candidate.save(update_fields=["status", "merged_into", "merge_reason"])


def _event_merge_score(first: TopicCluster, second: TopicCluster) -> float:
    first_tokens = set(first.entities or []) | set(first.keywords or [])
    second_tokens = set(second.entities or []) | set(second.keywords or [])
    if not first_tokens or not second_tokens:
        return 0.0
    return round(
        len(first_tokens & second_tokens) / len(first_tokens | second_tokens), 4
    )


def _link_reason(score: EventScore, threshold: float) -> dict[str, object]:
    return {
        "total_score": score.total,
        "embedding_score": score.embedding_score,
        "entity_score": score.entity_score,
        "title_score": score.title_score,
        "used_embedding": score.used_embedding,
        "threshold": threshold,
    }


def _link_role(event: TopicCluster) -> str:
    if not DocumentTopic.objects.filter(cluster=event).exists():
        return DocumentTopic.Role.REPRESENTATIVE
    return DocumentTopic.Role.EVIDENCE


def _mark_article_clustered(article: NormalizedDocument) -> None:
    article.status = NormalizedDocument.Status.CLUSTERED
    article.save(update_fields=["status"])


def _article_time(article: NormalizedDocument) -> datetime:
    return article.published_at or article.fetched_at or article.created_at


def _event_label(article: NormalizedDocument) -> str:
    return (article.title or article.canonical_url or f"article-{article.id}")[:240]


def _decimal(value: float) -> Decimal:
    return Decimal(str(round(value, 2)))
