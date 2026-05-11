"""Synchronous dashboard action services."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from django.conf import settings
from django.utils import timezone

from monitoring.alerts import evaluate_alert_rules
from monitoring.discovery import discover_source_candidates
from monitoring.enrichment import enrich_document
from monitoring.exporters import export_documents_artifact
from monitoring.models import ExportArtifact, NormalizedDocument
from monitoring.nlp.metrics import save_nlp_run_metric
from monitoring.nlp.pipeline import run_pipeline
from monitoring.reputation import score_source_reputations
from monitoring.sqlite_retry import run_with_sqlite_retry
from monitoring.topics import cluster_topics


@dataclass(frozen=True, slots=True)
class DashboardActionResult:
    """A short result for browser-triggered operations.

    Example:
        `result = DashboardActionResult("Enriched 3 documents")`
    """

    message: str
    detail: dict[str, object]


def run_enrich_documents_action(
    limit: int = 500, force: bool = False
) -> DashboardActionResult:
    """Run bounded enrichment from the dashboard.

    Example:
        `result = run_enrich_documents_action(limit=50)`
    """
    changed_count = 0
    documents = NormalizedDocument.objects.all()[:limit]
    for document in documents:
        changed_count += int(enrich_document(document, force=force))
    return DashboardActionResult(
        f"Enriched {changed_count} documents", {"changed": changed_count}
    )


def run_discover_sources_action(limit: int = 200) -> DashboardActionResult:
    """Run local source discovery from the dashboard.

    Example:
        `result = run_discover_sources_action(limit=200)`
    """
    created_count = discover_source_candidates(limit=limit)
    message = f"Discovered {created_count} source candidates"
    return DashboardActionResult(message, {"created": created_count})


def run_evaluate_alerts_action(lookback_hours: int = 24) -> DashboardActionResult:
    """Evaluate alert rules from the dashboard.

    Example:
        `result = run_evaluate_alerts_action(lookback_hours=24)`
    """
    created_count = run_with_sqlite_retry(
        lambda: evaluate_alert_rules(lookback_hours=lookback_hours)
    )
    message = f"Created {created_count} alert hits"
    return DashboardActionResult(message, {"created": created_count})


def run_cluster_topics_action(
    window_hours: int = 72,
    min_documents: int = 3,
) -> DashboardActionResult:
    """Build rolling topic clusters from the dashboard.

    Example:
        `result = run_cluster_topics_action(window_hours=72)`
    """
    cluster_count = cluster_topics(
        window_hours=window_hours, min_documents=min_documents
    )
    message = f"Built {cluster_count} topic clusters"
    return DashboardActionResult(message, {"clusters": cluster_count})


def run_score_reputation_action(window_days: int = 30) -> DashboardActionResult:
    """Score source reputation from the dashboard.

    Example:
        `result = run_score_reputation_action(window_days=30)`
    """
    scored_count = run_with_sqlite_retry(
        lambda: score_source_reputations(window_days=window_days)
    )
    message = f"Scored {scored_count} sources"
    return DashboardActionResult(message, {"sources": scored_count})


def run_export_parquet_action() -> tuple[DashboardActionResult, ExportArtifact]:
    """Export documents to Parquet from the dashboard.

    Example:
        `result, artifact = run_export_parquet_action()`
    """
    artifact = export_documents_artifact(_dashboard_export_path())
    message = f"Exported {artifact.row_count} rows to Parquet"
    result = DashboardActionResult(message, {"artifact_id": artifact.id})
    return result, artifact


def run_nlp_pipeline_action(text: str, tasks: str = "all") -> dict[str, object]:
    """Run the NLP pipeline from the dashboard and persist metrics.

    Example:
        `payload = run_nlp_pipeline_action("OpenAI update", "all")`
    """
    result = run_pipeline(text, tasks)
    metric = save_nlp_run_metric(result, "dashboard")
    result["metric_id"] = metric.id
    return result


def _dashboard_export_path() -> Path:
    stamp = timezone.now().strftime("%Y%m%d-%H%M%S")
    output_dir = Path(settings.PARQUET_EXPORT_DIR)
    return output_dir / f"documents-{stamp}.parquet"
