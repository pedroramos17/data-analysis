"""Row builders for comparison-machine Parquet datasets."""

from monitoring.models import (
    ArticleEntityMention,
    Claim,
    DocumentTopic,
    EventComparisonSnapshot,
    EventCoverage,
    NormalizedDocument,
    TopicCluster,
)

SUPPORTED_EXPORT_DATASETS = (
    "articles",
    "entities",
    "claims",
    "events",
    "article_event_links",
    "event_coverage",
    "event_comparison_snapshots",
)


def export_dataset_rows(dataset: str) -> list[dict[str, object]]:
    """Return Arrow-friendly rows for one supported dataset.

    Example:
        `rows = export_dataset_rows("articles")`
    """
    builders = _dataset_builders()
    if dataset not in builders:
        raise ValueError(
            f"Invalid dataset {dataset!r}; expected {SUPPORTED_EXPORT_DATASETS!r}"
        )
    return builders[dataset]()


def article_rows() -> list[dict[str, object]]:
    """Return article rows for analytical export.

    Example:
        `rows = article_rows()`
    """
    articles = NormalizedDocument.objects.select_related("source__provider__owner")
    return [_article_row(article) for article in articles]


def entity_rows() -> list[dict[str, object]]:
    """Return entity mention rows for analytical export.

    Example:
        `rows = entity_rows()`
    """
    mentions = ArticleEntityMention.objects.select_related("article", "entity")
    return [_entity_row(mention) for mention in mentions]


def claim_rows() -> list[dict[str, object]]:
    """Return claim rows for analytical export.

    Example:
        `rows = claim_rows()`
    """
    claims = Claim.objects.select_related("article__source__provider")
    return [_claim_row(claim) for claim in claims]


def event_rows() -> list[dict[str, object]]:
    """Return event rows for analytical export.

    Example:
        `rows = event_rows()`
    """
    return [_event_row(event) for event in TopicCluster.objects.all()]


def article_event_link_rows() -> list[dict[str, object]]:
    """Return article-event link rows for analytical export.

    Example:
        `rows = article_event_link_rows()`
    """
    links = DocumentTopic.objects.select_related("cluster", "document")
    return [_article_event_link_row(link) for link in links]


def event_coverage_rows() -> list[dict[str, object]]:
    """Return event coverage rows for analytical export.

    Example:
        `rows = event_coverage_rows()`
    """
    rows = EventCoverage.objects.select_related("event", "source", "provider", "owner")
    return [_event_coverage_row(row) for row in rows]


def event_comparison_snapshot_rows() -> list[dict[str, object]]:
    """Return event comparison snapshot rows for analytical export.

    Example:
        `rows = event_comparison_snapshot_rows()`
    """
    snapshots = EventComparisonSnapshot.objects.select_related("event")
    return [_event_comparison_snapshot_row(snapshot) for snapshot in snapshots]


def _dataset_builders() -> dict[str, object]:
    return {
        "articles": article_rows,
        "entities": entity_rows,
        "claims": claim_rows,
        "events": event_rows,
        "article_event_links": article_event_link_rows,
        "event_coverage": event_coverage_rows,
        "event_comparison_snapshots": event_comparison_snapshot_rows,
    }


def _article_row(article: NormalizedDocument) -> dict[str, object]:
    provider = article.source.provider
    return {
        "id": article.id,
        "source_id": article.source_id,
        "source_name": article.source.name,
        "provider_name": provider.name,
        "owner_name": provider.owner.name if provider.owner else "",
        "url": article.url,
        "canonical_url": article.canonical_url,
        "url_hash": article.url_hash,
        "title": article.title,
        "published_at": article.published_at,
        "fetched_at": article.fetched_at,
        "language": article.language,
        "content_hash": article.content_hash,
        "simhash": article.simhash,
        "status": article.status,
    }


def _entity_row(mention: ArticleEntityMention) -> dict[str, object]:
    return {
        "article_id": mention.article_id,
        "entity_id": mention.entity_id,
        "entity_name": mention.entity.name,
        "entity_type": mention.entity.entity_type,
        "mention_count": mention.mention_count,
        "backend": mention.backend,
    }


def _claim_row(claim: Claim) -> dict[str, object]:
    return {
        "id": claim.id,
        "article_id": claim.article_id,
        "provider_name": claim.article.source.provider.name,
        "claim_text": claim.claim_text,
        "normalized_claim": claim.normalized_claim,
        "claim_type": claim.claim_type,
        "backend": claim.backend,
    }


def _event_row(event: TopicCluster) -> dict[str, object]:
    return {
        "id": event.id,
        "label": event.label,
        "canonical_title": event.canonical_title,
        "status": event.status,
        "window_start": event.window_start,
        "window_end": event.window_end,
        "document_count": event.document_count,
        "source_count": event.source_count,
        "entities": event.entities,
    }


def _article_event_link_row(link: DocumentTopic) -> dict[str, object]:
    return {
        "event_id": link.cluster_id,
        "article_id": link.document_id,
        "similarity": float(link.similarity),
        "overlap_score": float(link.overlap_score),
        "role": link.role,
        "is_incorrect": link.is_incorrect,
        "link_reason": link.link_reason,
    }


def _event_coverage_row(row: EventCoverage) -> dict[str, object]:
    return {
        "event_id": row.event_id,
        "coverage_type": row.coverage_type,
        "source_id": row.source_id,
        "provider_id": row.provider_id,
        "owner_id": row.owner_id,
        "article_count": row.article_count,
        "amplification_score": row.amplification_score,
    }


def _event_comparison_snapshot_row(
    snapshot: EventComparisonSnapshot,
) -> dict[str, object]:
    return {
        "event_id": snapshot.event_id,
        "generated_at": snapshot.generated_at,
        "snapshot_hash": snapshot.snapshot_hash,
        "payload": snapshot.payload,
    }
