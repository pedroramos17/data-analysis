"""Admin workflows for source registry and ingestion review."""

from django.contrib import admin
from django.db.models import QuerySet
from django.http import HttpRequest
from django.utils import timezone

from monitoring.models import (
    CanonicalEntity,
    CanonicalUrl,
    CloudBudgetPolicy,
    CloudUsageLedger,
    ComputeProfileConfig,
    ComputeProfileTypeSetting,
    ComputeResourceSnapshot,
    DashboardSetting,
    DiscoveryCandidate,
    DocumentEnrichment,
    DailyDigest,
    DeadLetter,
    DigestCache,
    DocumentEntity,
    DocumentTopic,
    DocumentUrlReference,
    EntityAlias,
    EntityRelationship,
    ExportArtifact,
    FetchJob,
    IngestionCheckpoint,
    JobRunEvent,
    NlpRunMetric,
    NormalizedDocument,
    PipelineJob,
    RawEvent,
    Source,
    SourceReputationSnapshot,
    TopicCluster,
)
from monitoring.discovery import approve_discovery_candidate, reject_discovery_candidate


@admin.action(description="Disable selected sources")
def disable_sources(
    model_admin: admin.ModelAdmin,
    request: HttpRequest,
    queryset: QuerySet[Source],
) -> None:
    """Disable selected source registry entries.

    Example:
        Select sources in admin and run the action.
    """
    queryset.update(is_enabled=False)


@admin.action(description="Mark selected dead letters resolved")
def resolve_dead_letters(
    model_admin: admin.ModelAdmin,
    request: HttpRequest,
    queryset: QuerySet[DeadLetter],
) -> None:
    """Mark failed records as reviewed.

    Example:
        Select dead-letter rows in admin and run the action.
    """
    queryset.update(resolved_at=timezone.now())


@admin.action(description="Approve selected discovery candidates")
def approve_candidates(
    model_admin: admin.ModelAdmin,
    request: HttpRequest,
    queryset: QuerySet[DiscoveryCandidate],
) -> None:
    """Approve candidates and create disabled source rows.

    Example:
        Select candidates in admin and run the action.
    """
    for candidate in queryset:
        approve_discovery_candidate(candidate)


@admin.action(description="Reject selected discovery candidates")
def reject_candidates(
    model_admin: admin.ModelAdmin,
    request: HttpRequest,
    queryset: QuerySet[DiscoveryCandidate],
) -> None:
    """Reject selected discovery candidates.

    Example:
        Select candidates in admin and run the action.
    """
    for candidate in queryset:
        reject_discovery_candidate(candidate)


@admin.register(Source)
class SourceAdmin(admin.ModelAdmin):
    """Admin configuration for source registry records.

    Example:
        Open `/admin/monitoring/source/`.
    """

    list_display = (
        "name",
        "source_type",
        "category",
        "source_kind",
        "source_tier",
        "fetch_method",
        "reliability_score",
        "cadence_minutes",
        "health_status",
        "is_enabled",
    )
    list_filter = (
        "source_type",
        "category",
        "source_kind",
        "source_tier",
        "fetch_method",
        "is_enabled",
        "is_dynamic",
    )
    search_fields = ("name", "url")
    actions = [disable_sources]

    def health_status(self, source: Source) -> str:
        """Return source checkpoint health for admin lists.

        Example:
            Django calls this while rendering `SourceAdmin`.
        """
        checkpoint = IngestionCheckpoint.objects.filter(source=source).first()
        if checkpoint is None:
            return "never"
        if checkpoint.cooldown_until:
            return "cooldown"
        return checkpoint.last_status or "never"


@admin.register(RawEvent)
class RawEventAdmin(admin.ModelAdmin):
    """Admin view for raw payload snapshots.

    Example:
        Open `/admin/monitoring/rawevent/`.
    """

    list_display = ("source", "url", "http_status", "fetched_at", "content_hash")
    list_filter = ("source", "http_status")
    search_fields = ("url", "external_id", "content_hash")
    readonly_fields = ("content_hash", "fetched_at")


@admin.register(NormalizedDocument)
class NormalizedDocumentAdmin(admin.ModelAdmin):
    """Admin view for normalized review records.

    Example:
        Open `/admin/monitoring/normalizeddocument/`.
    """

    list_display = ("title", "source", "published_at", "language", "reviewed_at")
    list_filter = ("source", "language", "reviewed_at")
    search_fields = ("title", "canonical_url", "content", "author")
    readonly_fields = ("dedupe_hash", "created_at", "updated_at")


@admin.register(DocumentEnrichment)
class DocumentEnrichmentAdmin(admin.ModelAdmin):
    """Admin view for local enrichment metadata."""

    list_display = ("document", "detected_language", "sentiment_score", "updated_at")
    list_filter = ("detected_language", "enrichment_version")
    search_fields = ("document__title", "summary", "keywords", "quality_flags")


@admin.register(IngestionCheckpoint)
class IngestionCheckpointAdmin(admin.ModelAdmin):
    """Admin view for source checkpoint state.

    Example:
        Open `/admin/monitoring/ingestioncheckpoint/`.
    """

    list_display = (
        "source",
        "last_status",
        "consecutive_failures",
        "cooldown_until",
        "item_count",
        "last_attempt_at",
    )
    search_fields = ("source__name", "cursor", "error_message")


@admin.register(FetchJob)
class FetchJobAdmin(admin.ModelAdmin):
    """Admin view for job attempts and metrics.

    Example:
        Open `/admin/monitoring/fetchjob/`.
    """

    list_display = ("source", "status", "attempts", "created_at", "finished_at")
    list_filter = ("status", "source")
    search_fields = ("source__name", "error_message")


@admin.register(DeadLetter)
class DeadLetterAdmin(admin.ModelAdmin):
    """Admin view for failed pages and bad records.

    Example:
        Open `/admin/monitoring/deadletter/`.
    """

    list_display = ("source", "url", "created_at", "resolved_at")
    list_filter = ("source", "resolved_at")
    search_fields = ("url", "reason", "payload_excerpt")
    actions = [resolve_dead_letters]


@admin.register(DigestCache)
class DigestCacheAdmin(admin.ModelAdmin):
    """Admin view for cached digest payloads.

    Example:
        Open `/admin/monitoring/digestcache/`.
    """

    list_display = ("cache_key", "created_at", "expires_at")
    readonly_fields = ("created_at",)


@admin.register(CanonicalEntity)
class CanonicalEntityAdmin(admin.ModelAdmin):
    """Admin view for canonical entities.

    Example:
        Open `/admin/monitoring/canonicalentity/`.
    """

    list_display = ("name", "entity_type", "updated_at")
    list_filter = ("entity_type",)
    search_fields = ("name", "normalized_name")


@admin.register(EntityAlias)
class EntityAliasAdmin(admin.ModelAdmin):
    """Admin view for entity aliases.

    Example:
        Open `/admin/monitoring/entityalias/`.
    """

    list_display = ("alias", "entity")
    search_fields = ("alias", "alias_normalized", "entity__name")


@admin.register(DocumentEntity)
class DocumentEntityAdmin(admin.ModelAdmin):
    """Admin view for document entity mentions.

    Example:
        Open `/admin/monitoring/documententity/`.
    """

    list_display = ("document", "entity", "mention_count")
    search_fields = ("document__title", "entity__name", "mention_text")


@admin.register(EntityRelationship)
class EntityRelationshipAdmin(admin.ModelAdmin):
    """Admin view for entity relationship graph edges.

    Example:
        Open `/admin/monitoring/entityrelationship/`.
    """

    list_display = ("source_entity", "target_entity", "relationship_type", "weight")
    list_filter = ("relationship_type",)
    search_fields = ("source_entity__name", "target_entity__name")


@admin.register(DailyDigest)
class DailyDigestAdmin(admin.ModelAdmin):
    """Admin view for generated daily digests.

    Example:
        Open `/admin/monitoring/dailydigest/`.
    """

    list_display = ("digest_date", "title", "created_at")
    search_fields = ("title", "body")


@admin.register(DiscoveryCandidate)
class DiscoveryCandidateAdmin(admin.ModelAdmin):
    """Admin view for discovered source candidates."""

    list_display = ("name", "candidate_type", "status", "confidence", "category")
    list_filter = ("candidate_type", "status", "category")
    search_fields = ("name", "url", "evidence_url")
    actions = [approve_candidates, reject_candidates]


@admin.register(TopicCluster)
class TopicClusterAdmin(admin.ModelAdmin):
    """Admin view for rolling topic clusters."""

    list_display = (
        "canonical_title",
        "status",
        "document_count",
        "source_count",
        "trend_score",
        "novelty_score",
        "window_end",
    )
    list_filter = ("status",)
    search_fields = ("label", "canonical_title", "keywords", "entities")


@admin.register(DocumentTopic)
class DocumentTopicAdmin(admin.ModelAdmin):
    """Admin view for document-topic memberships."""

    list_display = ("cluster", "document", "role", "similarity", "overlap_score")
    list_filter = ("role",)
    search_fields = ("cluster__label", "document__title")


@admin.register(SourceReputationSnapshot)
class SourceReputationSnapshotAdmin(admin.ModelAdmin):
    """Admin view for reputation score history."""

    list_display = ("source", "score", "window_start", "window_end")
    search_fields = ("source__name", "components")


@admin.register(CanonicalUrl)
class CanonicalUrlAdmin(admin.ModelAdmin):
    """Admin view for canonical URL references."""

    list_display = ("domain", "canonical_url", "last_seen_at")
    list_filter = ("domain",)
    search_fields = ("canonical_url", "domain")


@admin.register(DocumentUrlReference)
class DocumentUrlReferenceAdmin(admin.ModelAdmin):
    """Admin view for document URL references."""

    list_display = ("document", "canonical_url", "reference_type")
    search_fields = ("document__title", "canonical_url__canonical_url")


@admin.register(ExportArtifact)
class ExportArtifactAdmin(admin.ModelAdmin):
    """Admin view for Parquet export artifacts."""

    list_display = ("export_type", "path", "row_count", "byte_size", "created_at")
    list_filter = ("export_type",)
    search_fields = ("path", "schema")


@admin.register(NlpRunMetric)
class NlpRunMetricAdmin(admin.ModelAdmin):
    """Admin view for offline NLP cost metrics."""

    list_display = ("entrypoint", "total_ms", "token_count", "success", "created_at")
    list_filter = ("entrypoint", "success")
    search_fields = ("text_hash", "error_message", "model_versions")


@admin.register(ComputeProfileTypeSetting)
class ComputeProfileTypeSettingAdmin(admin.ModelAdmin):
    """Admin view for editable compute profile type seeds."""

    list_display = (
        "slug",
        "label",
        "enabled",
        "backend_preference",
        "allow_cpu",
        "allow_gpu",
        "allow_cloud",
        "budget_guard_enabled",
        "updated_at",
    )
    list_filter = (
        "enabled",
        "backend_preference",
        "allow_cpu",
        "allow_gpu",
        "allow_cloud",
        "budget_guard_enabled",
    )
    search_fields = ("slug", "label", "description")



@admin.register(ComputeProfileConfig)
class ComputeProfileConfigAdmin(admin.ModelAdmin):
    """Admin view for dashboard compute profile limits."""

    list_display = (
        "name",
        "profile_type",
        "enabled",
        "backend_preference",
        "max_cpu_workers",
        "max_gpu_workers",
        "max_vram_gb",
        "cloud_enabled",
        "updated_at",
    )
    list_filter = (
        "profile_type",
        "enabled",
        "backend_preference",
        "cloud_enabled",
        "queue_enabled",
    )
    search_fields = ("name", "notes")


@admin.register(ComputeResourceSnapshot)
class ComputeResourceSnapshotAdmin(admin.ModelAdmin):
    """Admin view for captured compute capabilities."""

    list_display = (
        "hostname",
        "profile",
        "cpu_count",
        "gpu_available",
        "gpu_name",
        "gpu_total_vram_gb",
        "gpu_free_vram_gb",
        "cuda_available",
        "captured_at",
    )
    list_filter = (
        "gpu_available",
        "cuda_available",
        "torch_available",
        "cupy_available",
        "native_ctypes_available",
    )
    readonly_fields = ("captured_at",)
    search_fields = ("hostname", "gpu_name")


@admin.register(PipelineJob)
class PipelineJobAdmin(admin.ModelAdmin):
    """Admin view for dashboard-managed pipeline jobs."""

    list_display = (
        "job_name",
        "task_name",
        "profile",
        "backend",
        "status",
        "priority",
        "progress_percent",
        "estimated_cost_usd",
        "created_at",
        "started_at",
        "finished_at",
    )
    list_filter = ("status", "profile", "backend", "task_name")
    readonly_fields = ("created_at", "updated_at")
    search_fields = (
        "job_name",
        "task_name",
        "command",
        "manifest_path",
        "log_path",
        "error_message",
    )


@admin.register(JobRunEvent)
class JobRunEventAdmin(admin.ModelAdmin):
    """Admin view for append-only job execution events."""

    list_display = ("job", "event_type", "short_message", "created_at")
    list_filter = ("event_type", "job__status")
    readonly_fields = ("created_at",)
    search_fields = ("message", "job__job_name", "job__task_name")

    def short_message(self, event: JobRunEvent) -> str:
        """Return a one-line event preview.

        Example:
            `admin.short_message(event)` truncates long logs.
        """
        return event.message[:80]


@admin.register(CloudBudgetPolicy)
class CloudBudgetPolicyAdmin(admin.ModelAdmin):
    """Admin view for provider-neutral cloud budget policies."""

    list_display = (
        "name",
        "provider",
        "profile",
        "enabled",
        "max_total_cost_usd",
        "max_daily_cost_usd",
        "max_job_cost_usd",
        "require_manual_approval",
        "updated_at",
    )
    list_filter = (
        "enabled",
        "provider",
        "require_manual_approval",
        "stop_when_reached",
    )
    search_fields = ("name", "provider")


@admin.register(CloudUsageLedger)
class CloudUsageLedgerAdmin(admin.ModelAdmin):
    """Admin view for cloud cost and runtime ledger entries."""

    list_display = (
        "provider",
        "profile",
        "job",
        "usage_date",
        "cost_estimated_usd",
        "cost_actual_usd",
        "runtime_seconds",
        "created_at",
    )
    list_filter = ("provider", "usage_date", "profile")
    search_fields = ("provider", "job__job_name", "metadata_json")


@admin.register(DashboardSetting)
class DashboardSettingAdmin(admin.ModelAdmin):
    """Admin view for small dashboard settings."""

    list_display = ("key", "updated_at")
    readonly_fields = ("updated_at",)
    search_fields = ("key",)


from monitoring import alert_admin as _alert_admin  # noqa: E402,F401
from monitoring import orchestration_admin as _orchestration_admin  # noqa: E402,F401
