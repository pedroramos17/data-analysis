"""Shared helpers for Django-derived meta-factor rows."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from django.utils import timezone

from monitoring.models import DocumentTopic, NormalizedDocument, TopicCluster


@dataclass(frozen=True, slots=True)
class MetaFactorContext:
    """Time-bounded metadata extraction context.

    Example:
        `MetaFactorContext(now, start, end)`
    """

    as_of: datetime
    history_start: datetime
    history_end: datetime


def cluster_memberships(context: MetaFactorContext) -> list[DocumentTopic]:
    """Return event memberships available at the context timestamp.

    Example:
        `memberships = cluster_memberships(context)`
    """
    queryset = DocumentTopic.objects.select_related(
        "cluster", "document", "document__source"
    )
    queryset = queryset.filter(cluster__window_end__gte=context.history_start)
    queryset = queryset.filter(cluster__window_start__lte=context.history_end)
    return [item for item in queryset if _document_available(item.document, context)]


def event_clusters(context: MetaFactorContext) -> list[TopicCluster]:
    """Return event clusters available inside the context window.

    Example:
        `clusters = event_clusters(context)`
    """
    queryset = TopicCluster.objects.filter(window_end__gte=context.history_start)
    queryset = queryset.filter(window_start__lte=context.history_end)
    return [cluster for cluster in queryset if cluster.created_at <= context.as_of]


def document_available_at(document: NormalizedDocument) -> datetime:
    """Return the timestamp when a document became usable.

    Example:
        `available = document_available_at(document)`
    """
    return document.published_at or document.created_at or timezone.now()


def provider_name(document: NormalizedDocument) -> str:
    """Return provider using document metadata, then source fields.

    Example:
        `provider = provider_name(document)`
    """
    metadata_provider = str(document.metadata.get("provider", "")).strip()
    if metadata_provider:
        return metadata_provider
    query_provider = str(document.source.query_template or "").strip()
    return query_provider or document.source.name


def owner_name(document: NormalizedDocument) -> str:
    """Return owner using source affiliation, then provider.

    Example:
        `owner = owner_name(document)`
    """
    owner = str(document.metadata.get("owner", "")).strip()
    if owner:
        return owner
    affiliation = str(document.source.state_affiliation or "").strip()
    return affiliation or provider_name(document)


def peer_group(document: NormalizedDocument) -> str:
    """Return the default source peer group key.

    Example:
        `group = peer_group(document)`
    """
    source = document.source
    return "|".join([source.category, source.language or "", source.country or ""])


def frame_labels(document: NormalizedDocument) -> tuple[str, ...]:
    """Return deterministic frame labels from metadata or tags.

    Example:
        `labels = frame_labels(document)`
    """
    raw_frames = document.metadata.get("frames", [])
    if isinstance(raw_frames, list) and raw_frames:
        return tuple(str(frame).lower() for frame in raw_frames)
    return tuple(str(tag).lower() for tag in document.tags or ("unframed",))


def claim_labels(membership: DocumentTopic) -> tuple[str, ...]:
    """Return MVP claim labels from cluster keywords and document title.

    Example:
        `claims = claim_labels(membership)`
    """
    keywords = [str(value).lower() for value in membership.cluster.keywords[:3]]
    title_tokens = membership.document.title.lower().split()[:3]
    labels = keywords or title_tokens or ["claim"]
    return tuple(dict.fromkeys(labels))


def _document_available(
    document: NormalizedDocument, context: MetaFactorContext
) -> bool:
    available_at = document_available_at(document)
    return context.history_start <= available_at <= context.as_of
