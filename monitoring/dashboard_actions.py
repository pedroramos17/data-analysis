"""Synchronous dashboard action services."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from django.conf import settings
from django.utils import timezone

from monitoring.alerts import evaluate_alert_rules
from monitoring.catalog_sync import sync_catalogs
from monitoring.discovery import discover_source_candidates
from monitoring.enrichment import enrich_document
from monitoring.exporters import export_documents_artifact
from monitoring.ingestion import IngestionService
from monitoring.models import ExportArtifact, NormalizedDocument, Source
from monitoring.nlp.metrics import save_nlp_run_metric
from monitoring.nlp.pipeline import run_pipeline
from monitoring.orchestration.scheduler import enqueue_job
from monitoring.reputation import score_source_reputations
from monitoring.scheduling import find_due_sources
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


def run_ingest_sources_once_action(limit: int = 20) -> DashboardActionResult:
    """Run due source ingestion once from the dashboard.

    Example:
        `result = run_ingest_sources_once_action(limit=20)`
    """
    _sync_catalogs_when_source_registry_empty()
    sources = find_due_sources(timezone.now(), limit)
    succeeded_count, failed_count = _ingest_sources(sources)
    message = f"Ingested {succeeded_count} due sources; {failed_count} failed"
    return DashboardActionResult(
        message, {"succeeded": succeeded_count, "failed": failed_count}
    )


def run_ingest_sources_auto_run_action(limit: int = 20) -> DashboardActionResult:
    """Queue due source ingestion for a local dashboard worker.

    Example:
        `result = run_ingest_sources_auto_run_action(limit=20)`
    """
    command = f"python manage.py ingest_due_sources --limit {limit}"
    job = enqueue_job("ingestion", "local_cpu_low", "cpu", {"command": command})
    return DashboardActionResult(
        f"Queued source ingestion job {job.pk}", {"job_id": job.pk}
    )


def run_sync_catalogs_action(dry_run: bool = False) -> DashboardActionResult:
    """Synchronize JSON catalogs from the operations dashboard.

    Example:
        `result = run_sync_catalogs_action(dry_run=False)`
    """
    results = sync_catalogs(feeds=True, dry_run=dry_run)
    count = sum(result.source_count for result in results)
    mode = "validated" if dry_run else "synchronized"
    return DashboardActionResult(f"Catalogs {mode}: {count} feed rows", {"rows": count})


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
    slice_hours: int = 24,
) -> DashboardActionResult:
    """Update parent topic clusters and deterministic time slices.

    Example:
        `result = run_cluster_topics_action(window_hours=72, slice_hours=24)`
    """
    slice_count = cluster_topics(
        window_hours=window_hours,
        min_documents=min_documents,
        slice_hours=slice_hours,
    )
    message = f"Updated {slice_count} topic slices"
    return DashboardActionResult(message, {"slices": slice_count})


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


def _sync_catalogs_when_source_registry_empty() -> None:
    if Source.objects.filter(is_enabled=True).exists():
        return
    sync_catalogs(feeds=True, dry_run=False)


def _ingest_sources(sources: list[Source]) -> tuple[int, int]:
    service = IngestionService()
    succeeded_count = 0
    failed_count = 0
    for source in sources:
        try:
            service.ingest_source(source)
        except Exception:
            failed_count += 1
            continue
        succeeded_count += 1
    return succeeded_count, failed_count
