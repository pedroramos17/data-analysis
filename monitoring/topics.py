"""Deterministic local topic clustering."""

from collections import Counter
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from django.db import transaction
from django.db.models import QuerySet
from django.utils import timezone

from monitoring.enrichment import enrich_document
from monitoring.models import (
    DocumentEnrichment,
    DocumentTopic,
    NormalizedDocument,
    TopicCluster,
    TopicClusterSlice,
    TopicClusterSliceDocument,
)

REUSE_THRESHOLD = 0.60


@dataclass(slots=True)
class TopicBucket:
    """In-memory document bucket for deterministic clustering."""

    tokens: set[str]
    documents: list[NormalizedDocument]
    slice_start: datetime
    slice_end: datetime


def cluster_topics(
    window_hours: int = 72, min_documents: int = 3, slice_hours: int = 24
) -> int:
    """Build parent topic clusters and deterministic time slices.

    Example:
        `cluster_count = cluster_topics(window_hours=72, slice_hours=24)`
    """
    _validate_positive_int("slice_hours", slice_hours)
    window_end = timezone.now()
    window_start = window_end - timedelta(hours=window_hours)
    documents = _window_documents(window_start, window_end)
    buckets = _build_topic_buckets(documents, slice_hours)
    return _persist_topic_buckets(buckets, min_documents, window_hours, slice_hours)


def _validate_positive_int(name: str, value: int) -> None:
    if value > 0:
        return
    raise ValueError(f"Invalid {name}={value!r}; expected positive integer")


def _window_documents(
    window_start: datetime,
    window_end: datetime,
) -> QuerySet[NormalizedDocument]:
    return NormalizedDocument.objects.filter(
        created_at__gte=window_start,
        created_at__lte=window_end,
    ).select_related("source")


def _build_topic_buckets(
    documents: QuerySet[NormalizedDocument], slice_hours: int
) -> list[TopicBucket]:
    buckets: list[TopicBucket] = []
    for slice_start, slice_documents in _sliced_documents(documents, slice_hours):
        buckets.extend(_build_slice_buckets(slice_documents, slice_start, slice_hours))
    return buckets


def _sliced_documents(
    documents: QuerySet[NormalizedDocument], slice_hours: int
) -> list[tuple[datetime, list[NormalizedDocument]]]:
    slices: dict[datetime, list[NormalizedDocument]] = {}
    for document in documents:
        slice_start = _slice_start_for_document(document, slice_hours)
        slices.setdefault(slice_start, []).append(document)
    return sorted(slices.items(), key=lambda item: item[0])


def _build_slice_buckets(
    documents: list[NormalizedDocument], slice_start: datetime, slice_hours: int
) -> list[TopicBucket]:
    buckets: list[TopicBucket] = []
    slice_end = slice_start + timedelta(hours=slice_hours)
    for document in documents:
        enrich_document(document)
        tokens = _document_tokens(document)
        if tokens:
            _add_document_to_bucket(buckets, document, tokens, slice_start, slice_end)
    return buckets


def _add_document_to_bucket(
    buckets: list[TopicBucket],
    document: NormalizedDocument,
    tokens: set[str],
    slice_start: datetime,
    slice_end: datetime,
) -> None:
    for bucket in buckets:
        if len(bucket.tokens & tokens) >= 2:
            bucket.tokens |= tokens
            bucket.documents.append(document)
            return
    buckets.append(TopicBucket(tokens, [document], slice_start, slice_end))


def _persist_topic_buckets(
    buckets: list[TopicBucket],
    min_documents: int,
    window_hours: int,
    slice_hours: int,
) -> int:
    updated_count = 0
    for bucket in buckets:
        if len(bucket.documents) < min_documents:
            continue
        with transaction.atomic():
            _persist_topic_bucket(bucket, window_hours, slice_hours)
        updated_count += 1
    return updated_count


def _persist_topic_bucket(
    bucket: TopicBucket, window_hours: int, slice_hours: int
) -> None:
    cluster, duplicates = _resolve_parent_cluster(bucket, window_hours, slice_hours)
    _merge_duplicate_clusters(cluster, duplicates)
    topic_slice = _upsert_topic_slice(cluster, bucket, slice_hours)
    _replace_slice_document_topics(topic_slice, bucket, slice_hours)
    _sync_parent_document_topics(cluster)
    _refresh_parent_cluster(cluster, bucket, slice_hours)


def _resolve_parent_cluster(
    bucket: TopicBucket, window_hours: int, slice_hours: int
) -> tuple[TopicCluster, list[TopicCluster]]:
    scored = _eligible_parent_clusters(bucket, window_hours, slice_hours)
    if not scored:
        return _create_parent_cluster(bucket, slice_hours), []
    primary = _primary_parent_cluster(scored)
    duplicates = [cluster for cluster, _score in scored if cluster.pk != primary.pk]
    return primary, duplicates


def _eligible_parent_clusters(
    bucket: TopicBucket, window_hours: int, slice_hours: int
) -> list[tuple[TopicCluster, float]]:
    candidates = _candidate_parent_clusters(bucket, window_hours, slice_hours)
    scored = [(cluster, _topic_similarity(cluster, bucket)) for cluster in candidates]
    return [(cluster, score) for cluster, score in scored if score >= REUSE_THRESHOLD]


def _candidate_parent_clusters(
    bucket: TopicBucket, window_hours: int, slice_hours: int
) -> QuerySet[TopicCluster]:
    reuse_gap = timedelta(hours=max(window_hours, slice_hours * 2))
    return TopicCluster.objects.filter(
        status=TopicCluster.Status.ACTIVE,
        merged_into__isnull=True,
        last_seen_at__gte=bucket.slice_start - reuse_gap,
        first_seen_at__lte=bucket.slice_end + reuse_gap,
    )


def _primary_parent_cluster(scored: list[tuple[TopicCluster, float]]) -> TopicCluster:
    ranked = sorted(scored, key=lambda item: (item[0].pk or 0, -item[1]))
    return ranked[0][0]


def _create_parent_cluster(bucket: TopicBucket, slice_hours: int) -> TopicCluster:
    return TopicCluster.objects.create(
        label=_cluster_label(bucket),
        window_start=bucket.slice_start,
        window_end=bucket.slice_end,
        **_cluster_defaults(bucket, slice_hours),
    )


def _upsert_topic_slice(
    cluster: TopicCluster, bucket: TopicBucket, slice_hours: int
) -> TopicClusterSlice:
    topic_slice, _created = TopicClusterSlice.objects.update_or_create(
        cluster=cluster,
        slice_start=bucket.slice_start,
        slice_hours=slice_hours,
        defaults=_slice_defaults(bucket, slice_hours),
    )
    return topic_slice


def _replace_slice_document_topics(
    topic_slice: TopicClusterSlice, bucket: TopicBucket, slice_hours: int
) -> None:
    TopicClusterSliceDocument.objects.filter(slice=topic_slice).delete()
    for index, document in enumerate(bucket.documents):
        score = Decimal(str(_overlap_score(bucket, document)))
        TopicClusterSliceDocument.objects.create(
            slice=topic_slice,
            document=document,
            overlap_score=score,
            similarity=score,
            role=_document_role(index),
            metadata={"slice_hours": slice_hours},
        )


def _sync_parent_document_topics(cluster: TopicCluster) -> None:
    links = _cluster_slice_document_links(cluster)
    document_ids = [link.document_id for link in links]
    DocumentTopic.objects.filter(cluster=cluster).exclude(
        document_id__in=document_ids
    ).delete()
    for index, link in enumerate(links):
        _upsert_parent_document_topic(cluster, link, index)


def _cluster_slice_document_links(
    cluster: TopicCluster,
) -> list[TopicClusterSliceDocument]:
    links = TopicClusterSliceDocument.objects.filter(slice__cluster=cluster)
    return list(links.select_related("document").order_by("slice__slice_start", "id"))


def _upsert_parent_document_topic(
    cluster: TopicCluster, link: TopicClusterSliceDocument, index: int
) -> None:
    DocumentTopic.objects.update_or_create(
        cluster=cluster,
        document=link.document,
        defaults={
            "overlap_score": link.overlap_score,
            "similarity": link.similarity,
            "role": _document_role(index),
            "link_reason": {"method": "topic_slice", "slice_id": link.slice_id},
        },
    )


def _merge_duplicate_clusters(
    primary: TopicCluster, duplicates: list[TopicCluster]
) -> None:
    for duplicate in duplicates:
        _move_duplicate_parent_links(primary, duplicate)
        duplicate.status = TopicCluster.Status.MERGED
        duplicate.merged_into = primary
        duplicate.merge_reason = _merge_reason(primary)
        duplicate.save(update_fields=["status", "merged_into", "merge_reason"])


def _move_duplicate_parent_links(
    primary: TopicCluster, duplicate: TopicCluster
) -> None:
    for link in DocumentTopic.objects.filter(cluster=duplicate):
        DocumentTopic.objects.update_or_create(
            cluster=primary,
            document=link.document,
            defaults=_parent_link_defaults(link),
        )
    DocumentTopic.objects.filter(cluster=duplicate).delete()


def _parent_link_defaults(link: DocumentTopic) -> dict[str, object]:
    return {
        "overlap_score": link.overlap_score,
        "similarity": link.similarity,
        "role": link.role,
        "link_reason": link.link_reason,
    }


def _merge_reason(primary: TopicCluster) -> dict[str, object]:
    return {
        "method": "topic_slice_duplicate",
        "primary_id": primary.pk,
        "merged_at": timezone.now().isoformat(),
    }


def _refresh_parent_cluster(
    cluster: TopicCluster, bucket: TopicBucket, slice_hours: int
) -> None:
    documents = _parent_documents(cluster)
    if not documents:
        return
    cluster.window_start = min(cluster.window_start, bucket.slice_start)
    cluster.window_end = max(cluster.window_end, bucket.slice_end)
    cluster.first_seen_at = min(_document_time(document) for document in documents)
    cluster.last_seen_at = max(_document_time(document) for document in documents)
    _assign_parent_rollup(cluster, documents, bucket, slice_hours)
    cluster.save()


def _parent_documents(cluster: TopicCluster) -> list[NormalizedDocument]:
    links = DocumentTopic.objects.filter(cluster=cluster).select_related(
        "document__source"
    )
    return [link.document for link in links]


def _assign_parent_rollup(
    cluster: TopicCluster,
    documents: list[NormalizedDocument],
    bucket: TopicBucket,
    slice_hours: int,
) -> None:
    cluster.canonical_title = _representative_title(bucket)
    cluster.summary = _cluster_summary(bucket)
    cluster.topic_label = _cluster_label(bucket)
    cluster.keywords = _top_tokens_for_documents(documents)
    cluster.entities = _top_entities_for_documents(documents)
    cluster.document_count = len(documents)
    cluster.source_count = len({document.source_id for document in documents})
    cluster.representative_document = cluster.representative_document or documents[0]
    _assign_scores(cluster, documents)
    cluster.metadata = _parent_metadata(cluster, bucket, slice_hours)


def _assign_scores(cluster: TopicCluster, documents: list[NormalizedDocument]) -> None:
    trend_score = min(1, len(documents) / 10)
    cluster.score = Decimal(str(min(1, len(documents) / 10)))
    cluster.novelty_score = Decimal("0.75")
    cluster.trend_score = Decimal(str(trend_score))
    cluster.severity_score = Decimal(
        str(min(1, trend_score + cluster.source_count / 10))
    )
    cluster.confidence_score = Decimal(str(min(1, len(cluster.keywords) / 8)))


def _parent_metadata(
    cluster: TopicCluster, bucket: TopicBucket, slice_hours: int
) -> dict[str, object]:
    metadata = dict(cluster.metadata)
    metadata.update(
        {
            "method": "keyword_overlap",
            "slice_hours": slice_hours,
            "slice_count": cluster.slices.count(),
            "topic_signature": _topic_signature(bucket),
        }
    )
    return metadata


def _slice_defaults(bucket: TopicBucket, slice_hours: int) -> dict[str, object]:
    source_count = len({document.source_id for document in bucket.documents})
    trend_score = min(1, len(bucket.documents) / 10)
    return {
        "slice_end": bucket.slice_end,
        "keywords": _top_tokens(bucket),
        "entities": _top_entities(bucket),
        "document_count": len(bucket.documents),
        "source_count": source_count,
        "score": Decimal(str(min(1, len(bucket.documents) / 10))),
        "novelty_score": Decimal("0.75"),
        "trend_score": Decimal(str(trend_score)),
        "severity_score": Decimal(str(min(1, trend_score + source_count / 10))),
        "confidence_score": Decimal(str(min(1, len(bucket.tokens) / 8))),
        "metadata": _bucket_metadata(bucket, slice_hours),
        "first_seen_at": min(_document_time(document) for document in bucket.documents),
        "last_seen_at": max(_document_time(document) for document in bucket.documents),
    }


def _cluster_defaults(bucket: TopicBucket, slice_hours: int) -> dict[str, object]:
    source_count = len({document.source_id for document in bucket.documents})
    trend_score = min(1, len(bucket.documents) / 10)
    return {
        "canonical_title": _representative_title(bucket),
        "summary": _cluster_summary(bucket),
        "topic_label": _cluster_label(bucket),
        "keywords": _top_tokens(bucket),
        "entities": _top_entities(bucket),
        "document_count": len(bucket.documents),
        "source_count": source_count,
        "score": Decimal(str(min(1, len(bucket.documents) / 10))),
        "novelty_score": Decimal("0.75"),
        "trend_score": Decimal(str(trend_score)),
        "severity_score": Decimal(str(min(1, trend_score + source_count / 10))),
        "confidence_score": Decimal(str(min(1, len(bucket.tokens) / 8))),
        "metadata": _bucket_metadata(bucket, slice_hours),
        "first_seen_at": min(_document_time(document) for document in bucket.documents),
        "last_seen_at": max(_document_time(document) for document in bucket.documents),
    }


def _bucket_metadata(bucket: TopicBucket, slice_hours: int) -> dict[str, object]:
    return {
        "method": "keyword_overlap",
        "slice_hours": slice_hours,
        "topic_signature": _topic_signature(bucket),
        "document_ids": [document.pk for document in bucket.documents],
    }


def _topic_similarity(cluster: TopicCluster, bucket: TopicBucket) -> float:
    if cluster.metadata.get("topic_signature") == _topic_signature(bucket):
        return 1.0
    if _has_bucket_document_link(cluster, bucket):
        return 1.0
    keyword_score = _jaccard(set(cluster.keywords), set(_top_tokens(bucket)))
    entity_score = _jaccard(
        _lower_set(cluster.entities), _lower_set(_top_entities(bucket))
    )
    return round((0.70 * keyword_score) + (0.30 * entity_score), 4)


def _has_bucket_document_link(cluster: TopicCluster, bucket: TopicBucket) -> bool:
    document_ids = [document.pk for document in bucket.documents]
    return DocumentTopic.objects.filter(
        cluster=cluster, document_id__in=document_ids
    ).exists()


def _jaccard(first: set[str], second: set[str]) -> float:
    if not first or not second:
        return 0.0
    return len(first & second) / len(first | second)


def _lower_set(values: list[str]) -> set[str]:
    return {str(value).lower() for value in values}


def _document_tokens(document: NormalizedDocument) -> set[str]:
    enrichment = DocumentEnrichment.objects.filter(document=document).first()
    keywords = enrichment.keywords if enrichment else []
    entities = [str(entity).lower() for entity in document.entities]
    return set(str(token).lower() for token in list(keywords) + entities)


def _top_tokens(bucket: TopicBucket) -> list[str]:
    return _top_tokens_for_documents(bucket.documents)


def _top_tokens_for_documents(documents: list[NormalizedDocument]) -> list[str]:
    counts = Counter(
        token for document in documents for token in _document_tokens(document)
    )
    return [token for token, _count in counts.most_common(10)]


def _top_entities(bucket: TopicBucket) -> list[str]:
    return _top_entities_for_documents(bucket.documents)


def _top_entities_for_documents(documents: list[NormalizedDocument]) -> list[str]:
    counts = Counter(entity for document in documents for entity in document.entities)
    return [str(entity) for entity, _count in counts.most_common(10)]


def _cluster_label(bucket: TopicBucket) -> str:
    tokens = _top_tokens(bucket)[:3]
    return " / ".join(tokens)[:240] or "untitled"


def _topic_signature(bucket: TopicBucket) -> str:
    signature_tokens = sorted(_top_tokens(bucket)[:5])
    return "|".join(signature_tokens)


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


def _slice_start_for_document(
    document: NormalizedDocument, slice_hours: int
) -> datetime:
    document_time = _document_time(document)
    seconds = slice_hours * 3600
    timestamp = int(document_time.timestamp())
    slice_timestamp = timestamp - (timestamp % seconds)
    return datetime.fromtimestamp(slice_timestamp, tz=UTC)


def _document_time(document: NormalizedDocument) -> datetime:
    value = document.published_at or document.created_at
    if timezone.is_naive(value):
        return timezone.make_aware(value, UTC)
    return value.astimezone(UTC)
