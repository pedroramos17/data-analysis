"""Simple search, review, and operations pages."""

import json
from pathlib import Path

from django.contrib import messages
from django.db.models import Q, QuerySet
from django.http import HttpRequest, HttpResponseRedirect, JsonResponse
from django.shortcuts import redirect
from django.views.decorators.http import require_POST
from django.views.generic import DetailView, ListView, TemplateView

from monitoring.catalog_sync import ensure_catalogs_synced_if_enabled
from monitoring.dashboard_actions import (
    DashboardActionResult,
    run_cluster_topics_action,
    run_discover_sources_action,
    run_enrich_documents_action,
    run_evaluate_alerts_action,
    run_export_parquet_action,
    run_ingest_sources_auto_run_action,
    run_ingest_sources_once_action,
    run_nlp_pipeline_action,
    run_score_reputation_action,
    run_sync_catalogs_action,
)
from monitoring.dashboard_table_data import exports_table, metrics_table
from monitoring.digests import list_feed_digest_payload
from monitoring.exporters import read_parquet_preview
from monitoring.models import (
    AlertHit,
    DeadLetter,
    DiscoveryCandidate,
    ExportArtifact,
    IngestionCheckpoint,
    NlpRunMetric,
    NormalizedDocument,
    Source,
    SourceReputationSnapshot,
    TopicCluster,
)


class DashboardView(TemplateView):
    """Show operational controls and high-level system status.

    Example:
        Visit `/` to run bounded local maintenance actions.
    """

    template_name = "monitoring/dashboard.html"

    def get_context_data(self, **kwargs: object) -> dict[str, object]:
        """Add dashboard counts and the latest NLP result.

        Example:
            Django calls this while rendering the dashboard.
        """
        ensure_catalogs_synced_if_enabled()
        context = super().get_context_data(**kwargs)
        context["stats"] = _dashboard_stats()
        nlp_result = self.request.session.get("latest_nlp_result")
        context["nlp_result"] = nlp_result
        context["nlp_result_json"] = _pretty_json(nlp_result)
        recent_metrics = NlpRunMetric.objects.all()[:5]
        recent_exports = ExportArtifact.objects.all()[:5]
        context["recent_metrics"] = recent_metrics
        context["recent_exports"] = recent_exports
        context["recent_metrics_table"] = metrics_table(recent_metrics)
        context["recent_exports_table"] = exports_table(recent_exports)
        return context


class DocumentListView(ListView):
    """Search normalized documents by source, topic, date, and entity.

    Example:
        Visit `/documents/?q=security&source=1`.
    """

    model = NormalizedDocument
    paginate_by = 50
    template_name = "monitoring/document_list.html"
    context_object_name = "documents"

    def get_queryset(self) -> QuerySet[NormalizedDocument]:
        """Return filtered documents for the browse page.

        Example:
            Django calls this while rendering the list view.
        """
        queryset = self.model.objects.select_related("source")
        return _filter_documents(queryset, self.request)

    def get_context_data(self, **kwargs: object) -> dict[str, object]:
        """Add source filters to the document browse context.

        Example:
            Templates use `sources` for the source dropdown.
        """
        context = super().get_context_data(**kwargs)
        context["sources"] = Source.objects.filter(is_enabled=True)
        return context


class SourceListView(ListView):
    """List registered sources and schedules.

    Example:
        Visit `/sources/`.
    """

    model = Source
    paginate_by = 100
    template_name = "monitoring/source_list.html"
    context_object_name = "sources"

    def get_queryset(self) -> QuerySet[Source]:
        """Return sources ordered for operational review.

        Example:
            Django calls this while rendering the source list.
        """
        return self.model.objects.order_by("category", "source_tier", "name")


class SourceDetailView(DetailView):
    """Show source metadata and recent documents.

    Example:
        Visit `/sources/1/`.
    """

    model = Source
    template_name = "monitoring/source_detail.html"
    context_object_name = "source"

    def get_context_data(self, **kwargs: object) -> dict[str, object]:
        """Add recent normalized documents for the source.

        Example:
            Templates use `documents` for the recent table.
        """
        context = super().get_context_data(**kwargs)
        context["documents"] = self.object.normalizeddocument_set.all()[:50]
        context["checkpoint"] = IngestionCheckpoint.objects.filter(
            source=self.object
        ).first()
        context["reputation"] = SourceReputationSnapshot.objects.filter(
            source=self.object
        ).first()
        return context


class DeadLetterListView(ListView):
    """List unresolved failed fetches for review.

    Example:
        Visit `/failures/`.
    """

    model = DeadLetter
    paginate_by = 50
    template_name = "monitoring/dead_letter_list.html"
    context_object_name = "dead_letters"

    def get_queryset(self) -> QuerySet[DeadLetter]:
        """Return unresolved dead letters first.

        Example:
            Django calls this while rendering the failures page.
        """
        return self.model.objects.select_related("source").filter(
            resolved_at__isnull=True
        )


class AlertHitListView(ListView):
    """List in-app alert hits for review.

    Example:
        Visit `/alerts/?severity=high`.
    """

    model = AlertHit
    paginate_by = 50
    template_name = "monitoring/alert_hit_list.html"
    context_object_name = "alert_hits"

    def get_queryset(self) -> QuerySet[AlertHit]:
        """Return filtered alert hits for review.

        Example:
            Django calls this while rendering alerts.
        """
        queryset = self.model.objects.select_related(
            "rule", "detector", "cluster", "source", "representative_document"
        )
        queryset = _filter_alert_status(queryset, self.request.GET.get("status", ""))
        return _filter_alert_severity(queryset, self.request.GET.get("severity", ""))


class TopicClusterListView(ListView):
    """List active parent topic clusters.

    Example:
        Visit `/topics/`.
    """

    model = TopicCluster
    paginate_by = 50
    template_name = "monitoring/topic_cluster_list.html"
    context_object_name = "topic_clusters"

    def get_queryset(self) -> QuerySet[TopicCluster]:
        """Return active parent topics for the topic overview.

        Example:
            Django calls this while rendering `/topics/`.
        """
        return self.model.objects.filter(
            status=TopicCluster.Status.ACTIVE,
            merged_into__isnull=True,
        ).prefetch_related("slices")


class TopicClusterDetailView(DetailView):
    """Show a parent topic timeline with deterministic slices.

    Example:
        Visit `/topics/1/`.
    """

    model = TopicCluster
    template_name = "monitoring/topic_cluster_detail.html"
    context_object_name = "topic_cluster"

    def get_context_data(self, **kwargs: object) -> dict[str, object]:
        """Add slices and slice-document links to the detail page.

        Example:
            Templates iterate `topic_slices`.
        """
        context = super().get_context_data(**kwargs)
        context["topic_slices"] = self.object.slices.prefetch_related(
            "document_links__document"
        )
        return context


class ExportArtifactListView(ListView):
    """List Parquet exports created by commands or dashboard actions.

    Example:
        Visit `/exports/`.
    """

    model = ExportArtifact
    paginate_by = 50
    template_name = "monitoring/export_artifact_list.html"
    context_object_name = "exports"


class ExportArtifactDetailView(DetailView):
    """Show Parquet export schema and a small row preview.

    Example:
        Visit `/exports/1/`.
    """

    model = ExportArtifact
    template_name = "monitoring/export_artifact_detail.html"
    context_object_name = "artifact"

    def get_context_data(self, **kwargs: object) -> dict[str, object]:
        """Add a bounded Parquet preview to the artifact page.

        Example:
            Django calls this while rendering one export artifact.
        """
        context = super().get_context_data(**kwargs)
        context["preview"] = read_parquet_preview(Path(self.object.path), limit=25)
        return context


class FeedDigestView(TemplateView):
    """Show the cached categorized feed digest.

    Example:
        Visit `/digest/`.
    """

    template_name = "monitoring/feed_digest.html"

    def get_context_data(self, **kwargs: object) -> dict[str, object]:
        """Add digest payload to the page context.

        Example:
            Django calls this while rendering the digest page.
        """
        context = super().get_context_data(**kwargs)
        context["digest"] = list_feed_digest_payload()
        return context


def list_feed_digest_api(request: HttpRequest) -> JsonResponse:
    """Return categorized recent documents as JSON.

    Example:
        `GET /api/news/v1/list-feed-digest/`
    """
    return JsonResponse(list_feed_digest_payload())


@require_POST
def enrich_documents_action(request: HttpRequest) -> HttpResponseRedirect:
    """Run document enrichment and return to the dashboard.

    Example:
        `POST /actions/enrich-documents/`
    """
    result = run_enrich_documents_action(
        limit=_post_int(request, "limit", 500),
        force=bool(request.POST.get("force")),
    )
    return _action_redirect(request, result)


@require_POST
def discover_sources_action(request: HttpRequest) -> HttpResponseRedirect:
    """Run source discovery and return to the dashboard.

    Example:
        `POST /actions/discover-sources/`
    """
    result = run_discover_sources_action(limit=_post_int(request, "limit", 200))
    return _action_redirect(request, result)


@require_POST
def ingest_sources_run_once_action(request: HttpRequest) -> HttpResponseRedirect:
    """Ingest due enabled sources once from the dashboard.

    Example:
        `POST /actions/ingest-sources-run-once/`
    """
    result = run_ingest_sources_once_action(limit=_post_int(request, "limit", 20))
    return _action_redirect(request, result)


@require_POST
def ingest_sources_auto_run_action(request: HttpRequest) -> HttpResponseRedirect:
    """Queue due source ingestion for the local dashboard worker.

    Example:
        `POST /actions/ingest-sources-auto-run/`
    """
    result = run_ingest_sources_auto_run_action(limit=_post_int(request, "limit", 20))
    return _action_redirect(request, result)


@require_POST
def sync_catalogs_action(request: HttpRequest) -> HttpResponseRedirect:
    """Synchronize JSON catalogs into source rows from the dashboard.

    Example:
        `POST /actions/sync-catalogs/`
    """
    result = run_sync_catalogs_action(dry_run=bool(request.POST.get("dry_run")))
    return _action_redirect(request, result)


@require_POST
def evaluate_alerts_action(request: HttpRequest) -> HttpResponseRedirect:
    """Evaluate alert rules and return to the dashboard.

    Example:
        `POST /actions/evaluate-alerts/`
    """
    result = run_evaluate_alerts_action(
        lookback_hours=_post_int(request, "lookback_hours", 24)
    )
    return _action_redirect(request, result)


@require_POST
def cluster_topics_action(request: HttpRequest) -> HttpResponseRedirect:
    """Build topic clusters and return to the dashboard.

    Example:
        `POST /actions/cluster-topics/`
    """
    result = run_cluster_topics_action(
        window_hours=_post_int(request, "window_hours", 72),
        min_documents=_post_int(request, "min_documents", 3),
        slice_hours=_post_int(request, "slice_hours", 24),
    )
    return _action_redirect(request, result)


@require_POST
def score_source_reputation_action(request: HttpRequest) -> HttpResponseRedirect:
    """Score source reputation and return to the dashboard.

    Example:
        `POST /actions/score-source-reputation/`
    """
    result = run_score_reputation_action(
        window_days=_post_int(request, "window_days", 30)
    )
    return _action_redirect(request, result)


@require_POST
def export_parquet_action(request: HttpRequest) -> HttpResponseRedirect:
    """Create a Parquet export and open its preview page.

    Example:
        `POST /actions/export-parquet/`
    """
    result, artifact = run_export_parquet_action()
    messages.success(request, result.message)
    return redirect("monitoring:export-artifact-detail", pk=artifact.pk)


@require_POST
def nlp_pipeline_action(request: HttpRequest) -> HttpResponseRedirect:
    """Run the NLP pipeline and show JSON on the dashboard.

    Example:
        `POST /actions/nlp-pipeline/`
    """
    text = request.POST.get("text", "")
    tasks = request.POST.get("tasks", "all")
    request.session["latest_nlp_result"] = run_nlp_pipeline_action(text, tasks)
    messages.success(request, "NLP pipeline completed")
    return redirect("monitoring:dashboard")


def _filter_documents(
    queryset: QuerySet[NormalizedDocument],
    request: HttpRequest,
) -> QuerySet[NormalizedDocument]:
    queryset = _filter_by_search(queryset, request.GET.get("q", ""))
    queryset = _filter_by_source(queryset, request.GET.get("source", ""))
    queryset = _filter_by_language(queryset, request.GET.get("language", ""))
    return _filter_by_date(queryset, request.GET.get("date", ""))


def _filter_by_search(
    queryset: QuerySet[NormalizedDocument],
    query: str,
) -> QuerySet[NormalizedDocument]:
    if not query:
        return queryset
    return queryset.filter(
        Q(title__icontains=query)
        | Q(content__icontains=query)
        | Q(author__icontains=query)
        | Q(entities__icontains=query)
        | Q(tags__icontains=query)
    )


def _filter_by_source(
    queryset: QuerySet[NormalizedDocument],
    source_id: str,
) -> QuerySet[NormalizedDocument]:
    if not source_id:
        return queryset
    return queryset.filter(source_id=source_id)


def _filter_by_language(
    queryset: QuerySet[NormalizedDocument],
    language: str,
) -> QuerySet[NormalizedDocument]:
    if not language:
        return queryset
    return queryset.filter(language=language)


def _filter_by_date(
    queryset: QuerySet[NormalizedDocument],
    date_value: str,
) -> QuerySet[NormalizedDocument]:
    if not date_value:
        return queryset
    return queryset.filter(published_at__date=date_value)


def _dashboard_stats() -> dict[str, int]:
    return {
        "sources": Source.objects.count(),
        "enabled_sources": Source.objects.filter(is_enabled=True).count(),
        "documents": NormalizedDocument.objects.count(),
        "open_alerts": AlertHit.objects.filter(status=AlertHit.Status.OPEN).count(),
        "topic_clusters": TopicCluster.objects.filter(
            status=TopicCluster.Status.ACTIVE,
            merged_into__isnull=True,
        ).count(),
        "pending_candidates": DiscoveryCandidate.objects.filter(
            status="pending"
        ).count(),
        "exports": ExportArtifact.objects.count(),
    }


def _post_int(request: HttpRequest, name: str, default: int) -> int:
    value = request.POST.get(name, "")
    if not value:
        return default
    try:
        return int(value)
    except ValueError as error:
        raise ValueError(
            f"Invalid POST integer {name}={value!r}; expected int"
        ) from error


def _action_redirect(
    request: HttpRequest,
    result: DashboardActionResult,
) -> HttpResponseRedirect:
    messages.success(request, result.message)
    return redirect("monitoring:dashboard")


def _pretty_json(value: object) -> str:
    if value is None:
        return ""
    return json.dumps(value, indent=2, sort_keys=True)


def _filter_alert_status(
    queryset: QuerySet[AlertHit],
    status: str,
) -> QuerySet[AlertHit]:
    if not status:
        return queryset
    return queryset.filter(status=status)


def _filter_alert_severity(
    queryset: QuerySet[AlertHit],
    severity: str,
) -> QuerySet[AlertHit]:
    if not severity:
        return queryset
    return queryset.filter(severity=severity)
