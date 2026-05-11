"""Admin configuration for intelligent alert engine models."""

from django.contrib import admin
from django.db.models import QuerySet
from django.http import HttpRequest

from monitoring.alerts import (
    acknowledge_alert_hit,
    duplicate_alert_hit,
    ignore_alert_hit,
    resolve_alert_hit,
)
from monitoring.models import (
    AlertDetector,
    AlertFeedback,
    AlertHit,
    AlertHitDocument,
    AlertRule,
)


class AlertHitDocumentInline(admin.TabularInline):
    """Read-only evidence documents for an alert hit."""

    model = AlertHitDocument
    extra = 0
    can_delete = False
    readonly_fields = (
        "document",
        "role",
        "similarity_to_cluster",
        "source_reliability_score",
        "matched_text",
    )

    def has_add_permission(
        self, request: HttpRequest, obj: object | None = None
    ) -> bool:
        """Disable manual evidence creation."""
        return False


class AlertFeedbackInline(admin.TabularInline):
    """Human feedback captured for one alert hit."""

    model = AlertFeedback
    extra = 1
    fields = ("label", "comment", "user", "created_at")
    readonly_fields = ("created_at",)


@admin.action(description="Acknowledge selected alert hits")
def acknowledge_alerts(
    model_admin: admin.ModelAdmin,
    request: HttpRequest,
    queryset: QuerySet[AlertHit],
) -> None:
    """Mark alert hits acknowledged from admin."""
    for alert_hit in queryset:
        acknowledge_alert_hit(alert_hit)


@admin.action(description="Resolve selected alert hits")
def resolve_alerts(
    model_admin: admin.ModelAdmin,
    request: HttpRequest,
    queryset: QuerySet[AlertHit],
) -> None:
    """Mark alert hits resolved from admin."""
    for alert_hit in queryset:
        resolve_alert_hit(alert_hit)


@admin.action(description="Ignore selected alert hits")
def ignore_alerts(
    model_admin: admin.ModelAdmin,
    request: HttpRequest,
    queryset: QuerySet[AlertHit],
) -> None:
    """Mark alert hits ignored from admin."""
    for alert_hit in queryset:
        ignore_alert_hit(alert_hit)


@admin.action(description="Mark selected alert hits duplicate")
def duplicate_alerts(
    model_admin: admin.ModelAdmin,
    request: HttpRequest,
    queryset: QuerySet[AlertHit],
) -> None:
    """Mark alert hits duplicate from admin."""
    for alert_hit in queryset:
        duplicate_alert_hit(alert_hit)


@admin.register(AlertRule)
class AlertRuleAdmin(admin.ModelAdmin):
    """Admin view for explicit alert rules."""

    list_display = ("name", "rule_type", "severity", "enabled", "is_enabled")
    list_filter = ("rule_type", "severity", "enabled", "is_enabled", "category")
    search_fields = ("name", "description", "query")


@admin.register(AlertDetector)
class AlertDetectorAdmin(admin.ModelAdmin):
    """Admin view for automatic alert detectors."""

    list_display = ("name", "detector_type", "sensitivity", "enabled", "updated_at")
    list_filter = ("detector_type", "enabled")
    search_fields = ("name", "config")


@admin.register(AlertHit)
class AlertHitAdmin(admin.ModelAdmin):
    """Read-mostly admin view for generated alert hits."""

    list_display = (
        "title",
        "severity",
        "status",
        "trigger_type",
        "rule",
        "detector",
        "cluster",
        "confidence_score",
        "trend_score",
        "novelty_score",
        "occurred_at",
        "detected_at",
    )
    list_filter = (
        "severity",
        "status",
        "trigger_type",
        "rule",
        "detector",
        "occurred_at",
        "detected_at",
    )
    search_fields = (
        "title",
        "explanation",
        "cluster__canonical_title",
        "rule__name",
        "detector__name",
    )
    readonly_fields = (
        "title",
        "explanation",
        "score_breakdown",
        "trigger_summary",
        "cluster_summary",
        "evidence_documents",
        "severity_score",
        "confidence_score",
        "novelty_score",
        "trend_score",
        "source_diversity_score",
        "entity_importance_score",
        "market_relevance_score",
        "dedupe_key",
        "occurred_at",
        "detected_at",
    )
    inlines = [AlertHitDocumentInline, AlertFeedbackInline]
    actions = [acknowledge_alerts, resolve_alerts, ignore_alerts, duplicate_alerts]

    def has_add_permission(self, request: HttpRequest) -> bool:
        """Disable manual alert-hit creation."""
        return False

    def cluster_summary(self, alert_hit: AlertHit) -> str:
        """Return a compact cluster summary."""
        if not alert_hit.cluster:
            return "No cluster"
        return f"{alert_hit.cluster.canonical_title or alert_hit.cluster.label}"

    def evidence_documents(self, alert_hit: AlertHit) -> str:
        """Return evidence document count."""
        count = AlertHitDocument.objects.filter(alert_hit=alert_hit).count()
        return f"{count} evidence documents"

    def score_breakdown(self, alert_hit: AlertHit) -> dict[str, object]:
        """Return stored score components."""
        return alert_hit.metadata.get("score_breakdown", {})

    def trigger_summary(self, alert_hit: AlertHit) -> str:
        """Return the triggering rule or detector."""
        if alert_hit.rule:
            return f"Rule: {alert_hit.rule.name}"
        if alert_hit.detector:
            return f"Detector: {alert_hit.detector.name}"
        return "Invalid alert trigger"


@admin.register(AlertHitDocument)
class AlertHitDocumentAdmin(admin.ModelAdmin):
    """Admin view for alert evidence edges."""

    list_display = ("alert_hit", "document", "role", "similarity_to_cluster")
    search_fields = ("alert_hit__title", "document__title", "matched_text")


@admin.register(AlertFeedback)
class AlertFeedbackAdmin(admin.ModelAdmin):
    """Admin view for human alert feedback."""

    list_display = ("alert_hit", "label", "user", "created_at")
    list_filter = ("label",)
    search_fields = ("alert_hit__title", "comment")
