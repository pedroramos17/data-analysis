"""Admin registrations and actions for comparison-machine review."""

from django.contrib import admin
from django.db.models import QuerySet
from django.http import HttpRequest
from django.utils import timezone

from monitoring.models import (
    ArticleEmbedding,
    ArticleEntityMention,
    Claim,
    ClaimCluster,
    ClaimClusterMember,
    DocumentTopic,
    EventComparisonSnapshot,
    EventCoverage,
    FrameFeature,
    Owner,
    Provider,
    TopicCluster,
)


@admin.action(description="Merge selected events into the oldest event")
def merge_events(
    model_admin: admin.ModelAdmin,
    request: HttpRequest,
    queryset: QuerySet[TopicCluster],
) -> None:
    """Merge selected event clusters into the oldest selected cluster."""
    primary = queryset.order_by("id").first()
    if primary is None:
        return
    for event in queryset.exclude(pk=primary.pk):
        DocumentTopic.objects.filter(cluster=event).update(cluster=primary)
        event.status = TopicCluster.Status.MERGED
        event.merged_into = primary
        event.merge_reason = {"admin_action": "merge_events"}
        event.save(update_fields=["status", "merged_into", "merge_reason"])


@admin.action(description="Mark selected article-event links incorrect")
def mark_links_incorrect(
    model_admin: admin.ModelAdmin,
    request: HttpRequest,
    queryset: QuerySet[DocumentTopic],
) -> None:
    """Mark selected event links as reviewed and incorrect."""
    queryset.update(is_reviewed=True, is_incorrect=True, reviewed_at=timezone.now())


@admin.action(description="Split selected links into a new event")
def split_links_to_new_event(
    model_admin: admin.ModelAdmin,
    request: HttpRequest,
    queryset: QuerySet[DocumentTopic],
) -> None:
    """Move selected links into one new event cluster."""
    links = list(queryset.select_related("document", "cluster"))
    if not links:
        return
    event = _new_event_from_links(links)
    queryset.update(cluster=event, is_reviewed=True, reviewed_at=timezone.now())


@admin.action(description="Select selected link article as representative")
def select_representative_article(
    model_admin: admin.ModelAdmin,
    request: HttpRequest,
    queryset: QuerySet[DocumentTopic],
) -> None:
    """Use selected links as representative articles for their events."""
    for link in queryset.select_related("cluster", "document"):
        link.cluster.representative_document = link.document
        link.cluster.save(update_fields=["representative_document"])
        link.role = DocumentTopic.Role.REPRESENTATIVE
        link.save(update_fields=["role"])


def _new_event_from_links(links: list[DocumentTopic]) -> TopicCluster:
    first = links[0].document
    return TopicCluster.objects.create(
        label=first.title[:240],
        canonical_title=first.title,
        window_start=min(link.cluster.window_start for link in links),
        window_end=max(link.cluster.window_end for link in links),
        representative_document=first,
        first_seen_at=timezone.now(),
        last_seen_at=timezone.now(),
    )


@admin.register(Owner)
class OwnerAdmin(admin.ModelAdmin):
    """Admin view for source owners."""

    list_display = ("name", "country", "updated_at")
    search_fields = ("name", "canonical_name", "homepage_url", "notes")


@admin.register(Provider)
class ProviderAdmin(admin.ModelAdmin):
    """Admin view for source providers."""

    list_display = ("name", "owner", "domain", "updated_at")
    list_filter = ("owner",)
    search_fields = ("name", "canonical_name", "domain", "owner__name")


@admin.register(ArticleEntityMention)
class ArticleEntityMentionAdmin(admin.ModelAdmin):
    """Admin view for article entity mentions."""

    list_display = ("article", "entity", "mention_count", "backend")
    list_filter = ("backend",)
    search_fields = ("article__title", "entity__name", "mention_text")


@admin.register(ArticleEmbedding)
class ArticleEmbeddingAdmin(admin.ModelAdmin):
    """Admin view for article embeddings."""

    list_display = ("article", "backend", "dimensions", "updated_at")
    list_filter = ("backend",)
    search_fields = ("article__title", "model_name", "text_hash")


@admin.register(Claim)
class ClaimAdmin(admin.ModelAdmin):
    """Admin view for article claims."""

    list_display = ("article", "claim_type", "backend", "created_at")
    list_filter = ("claim_type", "backend")
    search_fields = ("article__title", "claim_text", "normalized_claim")


@admin.register(FrameFeature)
class FrameFeatureAdmin(admin.ModelAdmin):
    """Admin view for explainable framing features."""

    list_display = ("article", "feature_type", "value", "backend")
    list_filter = ("feature_type", "backend")
    search_fields = ("article__title", "feature_type", "evidence")


@admin.register(EventCoverage)
class EventCoverageAdmin(admin.ModelAdmin):
    """Admin view for event coverage aggregates."""

    list_display = ("event", "coverage_type", "provider", "owner", "article_count")
    list_filter = ("coverage_type", "provider", "owner")
    search_fields = ("event__label", "provider__name", "owner__name", "metadata")


@admin.register(ClaimCluster)
class ClaimClusterAdmin(admin.ModelAdmin):
    """Admin view for event claim clusters."""

    list_display = ("event", "provider_count", "article_count", "updated_at")
    search_fields = ("event__label", "representative_claim", "normalized_claim")


@admin.register(ClaimClusterMember)
class ClaimClusterMemberAdmin(admin.ModelAdmin):
    """Admin view for claim cluster memberships."""

    list_display = ("claim_cluster", "claim", "similarity")
    search_fields = ("claim_cluster__representative_claim", "claim__claim_text")


@admin.register(EventComparisonSnapshot)
class EventComparisonSnapshotAdmin(admin.ModelAdmin):
    """Admin view for provider comparison snapshots."""

    list_display = ("event", "generated_at", "snapshot_hash")
    readonly_fields = ("payload", "snapshot_hash", "generated_at")
    search_fields = ("event__label", "payload", "snapshot_hash")
