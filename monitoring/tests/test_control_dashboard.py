"""Tests for multi-profile dashboard orchestration."""

import json
from datetime import datetime, timedelta
from decimal import Decimal
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from monitoring.catalog_sync import CatalogSyncResult
from monitoring.cloud.budget import (
    apply_budget_guard,
    approve_cloud_job,
    get_budget_summary,
)
from monitoring.dashboard_models import CloudBudgetPolicy, PipelineJob
from monitoring.models import NormalizedDocument, RawEvent, Source, TopicCluster
from monitoring.orchestration.command_validation import validate_management_command
from monitoring.orchestration.job_templates import create_dashboard_jobs
from monitoring.orchestration.locks import acquire_lock, cleanup_expired_locks
from monitoring.orchestration.logging import update_progress_from_line
from monitoring.orchestration.profile_config import sync_default_profile_configs
from monitoring.orchestration.scheduler import claim_next_job, enqueue_job
from monitoring.orchestration.worker_state import (
    mark_stale_workers,
    register_worker,
)
from monitoring.orchestration_models import ResourceLock, WorkerHeartbeat
from monitoring.topics import cluster_topics


class DashboardOrchestrationTests(TestCase):
    """Scheduler, lock, and worker heartbeat regression tests."""

    def test_default_profiles_sync(self) -> None:
        """Default profile rows are created from compute profiles."""
        profiles = sync_default_profile_configs()

        self.assertEqual(len(profiles), 5)
        self.assertTrue(any(item.profile_type == "local_cpu_low" for item in profiles))

    def test_resource_lock_acquire_and_expiry(self) -> None:
        """A resource lock is unique until expiry cleanup removes it."""
        job = _job()
        lock = acquire_lock("cpu_pool:0", job, 30, "cpu-1")
        duplicate = acquire_lock("cpu_pool:0", job, 30, "cpu-2")
        ResourceLock.objects.filter(pk=lock.pk).update(
            expires_at=timezone.now() - timedelta(seconds=1)
        )

        removed = cleanup_expired_locks()

        self.assertIsNotNone(lock)
        self.assertIsNone(duplicate)
        self.assertEqual(removed, 1)

    def test_worker_heartbeat_can_be_marked_stale(self) -> None:
        """Old active worker heartbeats become stale."""
        worker = register_worker("cpu-1", "local_cpu_low")
        WorkerHeartbeat.objects.filter(pk=worker.pk).update(
            last_heartbeat_at=timezone.now() - timedelta(seconds=600)
        )

        stale_count = mark_stale_workers(ttl_seconds=120)
        worker.refresh_from_db()

        self.assertEqual(stale_count, 1)
        self.assertEqual(worker.status, WorkerHeartbeat.Status.STALE)

    def test_scheduler_claims_job_once(self) -> None:
        """Two workers cannot claim the same queued job."""
        _job()

        first = claim_next_job("cpu-1", "local_cpu_low")
        second = claim_next_job("cpu-2", "local_cpu_low")

        self.assertIsNotNone(first)
        self.assertIsNone(second)

    def test_progress_line_updates_job(self) -> None:
        """Structured progress lines update progress fields."""
        job = _job()

        updated = update_progress_from_line(job, "PROGRESS 20/100")
        job.refresh_from_db()

        self.assertTrue(updated)
        self.assertEqual(job.progress_current, 20)
        self.assertEqual(job.progress_total, 100)


class DashboardBudgetAndTemplateTests(TestCase):
    """Budget guard and job-template regression tests."""

    def test_command_validation_rejects_shell_operators(self) -> None:
        """Dashboard commands cannot include shell pipelines."""
        with self.assertRaisesMessage(ValueError, "shell operator"):
            validate_management_command("python manage.py inspect_compute | cat")

    def test_command_validation_rejects_denied_subcommands(self) -> None:
        """Dashboard commands cannot launch interactive Django shells."""
        with self.assertRaisesMessage(ValueError, "denied management command"):
            validate_management_command("python manage.py shell")

    def test_budget_guard_requires_manual_approval(self) -> None:
        """Cloud jobs stay waiting approval when policy requires approval."""
        job = _cloud_job()
        policy = _policy(job)

        check = apply_budget_guard(job, policy)
        job.refresh_from_db()

        self.assertFalse(check.allowed)
        self.assertEqual(job.status, PipelineJob.Status.WAITING_APPROVAL)

    def test_approval_moves_cloud_job_to_queued(self) -> None:
        """Approved zero-cost cloud jobs can move to queued."""
        job = _cloud_job()
        _policy(job)

        approve_cloud_job(job, "tester")
        job.refresh_from_db()

        self.assertEqual(job.status, PipelineJob.Status.QUEUED)

    def test_budget_summary_reports_waiting_jobs(self) -> None:
        """Budget summaries include waiting approval counts."""
        job = _cloud_job()
        policy = _policy(job)
        apply_budget_guard(job, policy)

        summary = get_budget_summary(policy)

        self.assertEqual(summary["jobs_waiting_approval"], 1)

    def test_local_template_creates_safe_jobs(self) -> None:
        """The local simple template creates only local non-cloud jobs."""
        with TemporaryDirectory() as directory:
            with override_settings(PARQUET_EXPORT_DIR=Path(directory)):
                result = create_dashboard_jobs(
                    "local_simple_pipeline",
                    "local_cpu_low",
                )

        self.assertEqual(len(result["job_ids"]), 7)
        self.assertFalse(PipelineJob.objects.filter(backend="cloud").exists())

    def test_cloud_template_defaults_to_waiting_approval(self) -> None:
        """Cloud templates write jobs guarded by manual approval."""
        with TemporaryDirectory() as directory:
            with override_settings(PARQUET_EXPORT_DIR=Path(directory)):
                create_dashboard_jobs("cloud_student_advanced_plan", "cloud_student")

        self.assertTrue(
            PipelineJob.objects.filter(
                status=PipelineJob.Status.WAITING_APPROVAL
            ).exists()
        )

    def test_template_dry_run_creates_no_jobs(self) -> None:
        """Dry-run previews do not write PipelineJob rows."""
        result = create_dashboard_jobs(
            "mx350_micro_gpu_test", "local_mx350_queue", True
        )

        self.assertEqual(result["job_ids"], [])
        self.assertEqual(PipelineJob.objects.count(), 0)


class DashboardViewAndApiTests(TestCase):
    """Server-rendered dashboard and internal API regression tests."""

    def test_dashboard_pages_render(self) -> None:
        """Control dashboard pages are routable."""
        route_names = (
            "control-dashboard",
            "control-profiles",
            "control-resources",
            "control-jobs",
            "control-cloud-budget",
            "control-pipeline-plan",
            "control-artifacts",
            "control-workers",
        )

        for route_name in route_names:
            response = self.client.get(reverse(f"monitoring:{route_name}"))
            self.assertEqual(response.status_code, 200)

    def test_operations_dashboard_shows_source_controls(self) -> None:
        """Operations Dashboard exposes source ingestion and catalog controls."""
        response = self.client.get(reverse("monitoring:dashboard"))
        content = response.content.decode()

        self.assertEqual(response.status_code, 200)
        self.assertIn("Run once", content)
        self.assertIn("Queue auto-run", content)
        self.assertIn("Sync catalogs", content)
        self.assertIn("Topic slice hours", content)
        self.assertIn("Update topic slices", content)
        self.assertIn("data-table-shell", content)

    def test_topic_pages_show_parent_and_slice_timeline(self) -> None:
        """Topic pages show parent rows and slice timeline details."""
        first_time = timezone.now() - timedelta(hours=2)
        _document(title="OpenAI breach report", published_at=first_time)
        _document(title="OpenAI breach response", published_at=first_time)
        cluster_topics(window_hours=72, min_documents=2, slice_hours=24)
        cluster = TopicCluster.objects.get()

        list_response = self.client.get(reverse("monitoring:topic-cluster-list"))
        detail_response = self.client.get(
            reverse("monitoring:topic-cluster-detail", kwargs={"pk": cluster.pk})
        )

        self.assertEqual(list_response.status_code, 200)
        self.assertContains(list_response, "Latest slice")
        self.assertContains(list_response, "Timeline")
        self.assertEqual(detail_response.status_code, 200)
        self.assertContains(detail_response, "Topic timeline")
        self.assertContains(detail_response, "Slice window")

    def test_run_once_sources_action_uses_ingestion_service(self) -> None:
        """Run once ingests due sources without creating a PipelineJob."""
        source = _source("Example Feed")
        FakeIngestionService.ingested_names = []

        with patch(
            "monitoring.dashboard_actions.find_due_sources", return_value=[source]
        ):
            with patch(
                "monitoring.dashboard_actions.IngestionService", FakeIngestionService
            ):
                response = self.client.post(
                    reverse("monitoring:ingest-sources-run-once-action"),
                    data={"limit": "1"},
                )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(FakeIngestionService.ingested_names, ["Example Feed"])
        self.assertEqual(PipelineJob.objects.count(), 0)

    def test_auto_run_sources_action_queues_worker_job(self) -> None:
        """Auto-run creates a validated local CPU ingestion job."""
        response = self.client.post(
            reverse("monitoring:ingest-sources-auto-run-action"),
            data={"limit": "3"},
        )
        job = PipelineJob.objects.get(task_name="ingestion")

        self.assertEqual(response.status_code, 302)
        self.assertEqual(job.status, PipelineJob.Status.QUEUED)
        self.assertIn("ingest_due_sources --limit 3", job.command)

    def test_sync_catalogs_action_calls_sync_service(self) -> None:
        """Catalog sync action delegates to the central sync service."""
        result = CatalogSyncResult("worldmonitor_feeds", 2, False, True, "abc")

        with patch(
            "monitoring.dashboard_actions.sync_catalogs", return_value=(result,)
        ):
            response = self.client.post(reverse("monitoring:sync-catalogs-action"))

        self.assertEqual(response.status_code, 302)

    def test_control_dashboard_uses_resizable_table_component(self) -> None:
        """Control dashboard renders shared data-table shells."""
        response = self.client.get(reverse("monitoring:control-dashboard"))
        content = response.content.decode()

        self.assertEqual(response.status_code, 200)
        self.assertIn("data-table-shell", content)
        self.assertIn("column-resizer", content)

    def test_jobs_api_rejects_unsafe_command(self) -> None:
        """API job creation rejects unsafe command strings."""
        payload = {
            "task_name": "export_parquet",
            "profile": "local_cpu_low",
            "backend": "cpu",
            "params": {"command": "python manage.py inspect_compute | cat"},
        }

        response = self.client.post(
            reverse("monitoring:dashboard-api-jobs"),
            data=json.dumps(payload),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 400)

    def test_status_api_returns_dashboard_payload(self) -> None:
        """Dashboard status API returns jobs, resources, budgets, and artifacts."""
        response = self.client.get(reverse("monitoring:dashboard-api-status"))

        self.assertEqual(response.status_code, 200)
        self.assertIn("jobs", response.json())
        self.assertIn("latest_artifacts", response.json())


class FakeIngestionService:
    """Named fake ingestion service for dashboard action tests."""

    ingested_names: list[str] = []

    def ingest_source(self, source: Source) -> None:
        """Record ingested source names without external I/O."""
        self.__class__.ingested_names.append(source.name)


def _job() -> PipelineJob:
    sync_default_profile_configs()
    return enqueue_job(
        "export_parquet",
        "local_cpu_low",
        "cpu",
        {"command": "python manage.py inspect_compute --profile local_cpu_low"},
    )


def _cloud_job() -> PipelineJob:
    sync_default_profile_configs()
    return enqueue_job(
        "advanced_dtcwt",
        "cloud_student",
        "cloud",
        {
            "command": "python manage.py run_analytics_pipeline --profile cloud_student",
            "estimated_cost_usd": "0",
            "provider": "provider_neutral",
        },
    )


def _source(name: str) -> Source:
    return Source.objects.create(
        name=name,
        url="https://example.org/feed.xml",
        source_type=Source.SourceType.RSS,
        fetch_method=Source.FetchMethod.HTTP,
    )


def _document(
    title: str,
    published_at: datetime,
) -> NormalizedDocument:
    source = _source(f"Topic Source {RawEvent.objects.count()}")
    raw_event = RawEvent.objects.create(
        source=source,
        url=f"https://example.org/topic-{RawEvent.objects.count()}",
        content_hash=f"topic-raw-{RawEvent.objects.count()}",
        payload_text="{}",
    )
    return NormalizedDocument.objects.create(
        source=source,
        raw_event=raw_event,
        canonical_url=raw_event.url,
        title=title,
        published_at=published_at,
        content="Security breach risk improves with OpenAI response.",
        entities=["OpenAI"],
        tags=["security"],
        dedupe_hash=f"topic-doc-{raw_event.id}",
    )


def _policy(job: PipelineJob) -> CloudBudgetPolicy:
    return CloudBudgetPolicy.objects.create(
        name="test cloud policy",
        enabled=True,
        provider="provider_neutral",
        profile=job.profile,
        max_total_cost_usd=Decimal("0"),
        max_daily_cost_usd=Decimal("0"),
        max_job_cost_usd=Decimal("0"),
        allowed_tasks_json=["advanced_dtcwt"],
        require_manual_approval=True,
    )
