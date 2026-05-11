"""Deterministic local topic clustering."""

from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal

from django.db.models import QuerySet
from django.utils import timezone

from monitoring.enrichment import enrich_document
from monitoring.models import (
    DocumentEnrichment,
    DocumentTopic,
    NormalizedDocument,
    TopicCluster,
)


@dataclass(slots=True)
class TopicBucket:
    """In-memory document bucket for deterministic clustering."""

    tokens: set[str]
    documents: list[NormalizedDocument]


def cluster_topics(window_hours: int = 72, min_documents: int = 3) -> int:
    """Build topic clusters from local keywords and entities.

    Example:
        `cluster_count = cluster_topics(window_hours=72, min_documents=3)`
    """
    window_end = timezone.now()
    window_start = window_end - timedelta(hours=window_hours)
    documents = _window_documents(window_start, window_end)
    buckets = _build_topic_buckets(documents)
    return _persist_topic_buckets(buckets, window_start, window_end, min_documents)


def _window_documents(
    window_start: datetime,
    window_end: datetime,
) -> QuerySet[NormalizedDocument]:
    return NormalizedDocument.objects.filter(
        created_at__gte=window_start,
        created_at__lte=window_end,
    ).select_related("source")


def _build_topic_buckets(documents: QuerySet[NormalizedDocument]) -> list[TopicBucket]:
    buckets: list[TopicBucket] = []
    for document in documents:
        enrich_document(document)
        tokens = _document_tokens(document)
        if not tokens:
            continue
        _add_document_to_bucket(buckets, document, tokens)
    return buckets


def _add_document_to_bucket(
    buckets: list[TopicBucket],
    document: NormalizedDocument,
    tokens: set[str],
) -> None:
    for bucket in buckets:
        if len(bucket.tokens & tokens) >= 2:
            bucket.tokens |= tokens
            bucket.documents.append(document)
            return
    buckets.append(TopicBucket(tokens=tokens, documents=[document]))


def _persist_topic_buckets(
    buckets: list[TopicBucket],
    window_start: datetime,
    window_end: datetime,
    min_documents: int,
) -> int:
    created_count = 0
    for bucket in buckets:
        if len(bucket.documents) < min_documents:
            continue
        cluster = _upsert_topic_cluster(bucket, window_start, window_end)
        _replace_document_topics(cluster, bucket)
        created_count += 1
    return created_count


def _upsert_topic_cluster(
    bucket: TopicBucket,
    window_start: datetime,
    window_end: datetime,
) -> TopicCluster:
    label = _cluster_label(bucket)
    cluster, _created = TopicCluster.objects.update_or_create(
        label=label,
        window_start=window_start,
        defaults=_cluster_defaults(bucket, window_end),
    )
    return cluster


def _replace_document_topics(cluster: TopicCluster, bucket: TopicBucket) -> None:
    DocumentTopic.objects.filter(cluster=cluster).delete()
    for index, document in enumerate(bucket.documents):
        DocumentTopic.objects.create(
            cluster=cluster,
            document=document,
            overlap_score=Decimal(str(_overlap_score(bucket, document))),
            similarity=Decimal(str(_overlap_score(bucket, document))),
            role=_document_role(index),
        )


def _cluster_defaults(bucket: TopicBucket, window_end: datetime) -> dict[str, object]:
    title = _representative_title(bucket)
    source_count = len({document.source_id for document in bucket.documents})
    trend_score = min(1, len(bucket.documents) / 10)
    return {
        "canonical_title": title,
        "summary": _cluster_summary(bucket),
        "topic_label": _cluster_label(bucket),
        "window_end": window_end,
        "keywords": _top_tokens(bucket),
        "entities": _top_entities(bucket),
        "document_count": len(bucket.documents),
        "source_count": source_count,
        "score": Decimal(str(min(1, len(bucket.documents) / 10))),
        "novelty_score": Decimal("0.75"),
        "trend_score": Decimal(str(trend_score)),
        "severity_score": Decimal(str(min(1, trend_score + source_count / 10))),
        "confidence_score": Decimal(str(min(1, len(bucket.tokens) / 8))),
        "metadata": {"method": "keyword_overlap"},
        "last_seen_at": window_end,
    }


def _document_tokens(document: NormalizedDocument) -> set[str]:
    enrichment = DocumentEnrichment.objects.filter(document=document).first()
    keywords = enrichment.keywords if enrichment else []
    entities = [str(entity).lower() for entity in document.entities]
    return set(str(token).lower() for token in list(keywords) + entities)


def _top_tokens(bucket: TopicBucket) -> list[str]:
    counts = Counter(
        token for document in bucket.documents for token in _document_tokens(document)
    )
    return [token for token, _count in counts.most_common(10)]


def _top_entities(bucket: TopicBucket) -> list[str]:
    counts = Counter(
        entity for document in bucket.documents for entity in document.entities
    )
    return [str(entity) for entity, _count in counts.most_common(10)]


def _cluster_label(bucket: TopicBucket) -> str:
    tokens = _top_tokens(bucket)[:3]
    return " / ".join(tokens)[:240] or "untitled"


def _overlap_score(bucket: TopicBucket, document: NormalizedDocument) -> float:
    tokens = _document_tokens(document)
    if not tokens:
        return 0.0
    return round(len(tokens & bucket.tokens) / len(tokens), 2)


def _document_role(index: int) -> str:
    if index == 0:
        return DocumentTopic.Role.REPRESENTATIVE
    return DocumentTopic.Role.EVIDENCE


def _representative_title(bucket: TopicBucket) -> str:
    if not bucket.documents:
        return "Untitled event cluster"
    return bucket.documents[0].title


def _cluster_summary(bucket: TopicBucket) -> str:
    snippets = [document.content or document.title for document in bucket.documents[:3]]
    summary = " ".join(snippet for snippet in snippets if snippet)
    return summary[:700]
