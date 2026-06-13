"""Phase 13 orchestration tests.

Covers the Task 13.1 acceptance criteria: each stage runs independently, failed
stages are retryable, job state is visible, and logs include document ids and
model versions. Also unit-tests the rate-limit policy deterministically.
"""

from __future__ import annotations

from io import StringIO

from django.core.management import call_command
from django.test import TestCase

from sourceflow import models
from sourceflow.orchestration import (
    PipelineRunner,
    RateLimitExceeded,
    RateLimitPolicy,
    RetryPolicy,
    job_state,
)
from sourceflow.orchestration.stages import STAGE_ORDER


class FakeClock:
    def __init__(self) -> None:
        self.t = 0.0

    def __call__(self) -> float:
        return self.t

    def advance(self, seconds: float) -> None:
        self.t += seconds


class Phase13RateLimitPolicyTests(TestCase):
    def test_token_bucket_throttles_and_refills_without_sleeping(self) -> None:
        clock = FakeClock()
        policy = RateLimitPolicy(capacity=1, refill_rate=1.0, clock=clock, sleep=lambda s: None)

        self.assertTrue(policy.try_acquire())   # consume the only token
        self.assertFalse(policy.try_acquire())  # empty -> throttled
        with self.assertRaises(RateLimitExceeded):
            policy.acquire(block=False)

        clock.advance(1.0)                       # one token refills
        self.assertTrue(policy.try_acquire())


class Phase13OrchestrationTests(TestCase):
    def setUp(self) -> None:
        self.source = models.Source.objects.create(
            name="Wire A",
            url="https://example.test/wire-a.xml",
            source_type=models.Source.SourceType.RSS,
            language="en",
        )
        self.payload = {
            "source_id": self.source.pk,
            "raw_text": "Petrobras faces a regulatory investigation.",
            "title": "Petrobras probe",
            "url": "https://example.test/probe",
        }

    def test_full_run_succeeds_with_visible_state_and_report(self) -> None:
        runner = PipelineRunner()
        job = runner.create_job(self.payload)

        # Before running: every stage is pending and visible.
        self.assertEqual(job.stage_runs.count(), len(STAGE_ORDER))
        self.assertEqual(
            {r.status for r in job.stage_runs.all()},
            {models.PipelineStageRun.Status.PENDING},
        )

        runner.run(job)

        job.refresh_from_db()
        self.assertEqual(job.status, models.PipelineJob.Status.SUCCEEDED)
        self.assertIsNotNone(job.document_id)
        # All stages succeeded; state is fully visible.
        self.assertEqual(
            {r.status for r in job.stage_runs.all()},
            {models.PipelineStageRun.Status.SUCCEEDED},
        )
        # The pipeline actually did the work end-to-end.
        self.assertGreaterEqual(models.Claim.objects.filter(document_id=job.document_id).count(), 1)
        self.assertGreaterEqual(models.Event.objects.filter(document_id=job.document_id).count(), 1)
        self.assertTrue(job.report_json)
        self.assertEqual(job.report_json["document_id"], job.document_id)

    def test_each_stage_records_model_versions(self) -> None:
        runner = PipelineRunner()
        job = runner.create_job(self.payload)
        runner.run(job)

        state = job_state(job)
        by_stage = {entry["stage"]: entry for entry in state["stages"]}
        self.assertIn("claim_extractor", by_stage["extract_claims"]["model_versions"])
        self.assertIn("ingestion_version", by_stage["normalize"]["model_versions"])
        self.assertIn("event_extractor", by_stage["extract_events"]["model_versions"])

    def test_stage_runs_independently_and_failed_stage_is_retryable(self) -> None:
        runner = PipelineRunner(retry_policy=RetryPolicy(max_attempts=2))
        job = runner.create_job(self.payload)

        # Run a downstream stage with no document yet -> it fails (independently
        # invocable), and the retry policy is exercised (2 attempts recorded).
        failed = runner.run_stage(job, "extract_claims")
        self.assertEqual(failed.status, models.PipelineStageRun.Status.FAILED)
        self.assertEqual(failed.attempts, 2)
        job.refresh_from_db()
        self.assertEqual(job.status, models.PipelineJob.Status.FAILED)

        # Provide the prerequisite by running the upstream stages, then retry.
        runner.run_stage(job, "ingest")
        runner.run_stage(job, "normalize")
        runner.run_stage(job, "chunk")
        retried = runner.retry_stage(job, "extract_claims")

        self.assertEqual(retried.status, models.PipelineStageRun.Status.SUCCEEDED)
        self.assertGreaterEqual(retried.output_json["claims"], 1)

    def test_logs_include_document_id_and_model_versions(self) -> None:
        runner = PipelineRunner()
        job = runner.create_job(self.payload)

        with self.assertLogs("sourceflow.orchestration", level="INFO") as captured:
            runner.run(job)

        joined = "\n".join(captured.output)
        self.assertIn("document_id=", joined)
        self.assertIn("model_versions=", joined)
        self.assertIn("stage_ok", joined)

    def test_cli_runs_pipeline_and_reports_status(self) -> None:
        out = StringIO()
        call_command(
            "run_pipeline",
            f"--source-id={self.source.pk}",
            "--raw-text=Petrobras faces a regulatory investigation.",
            "--title=Probe",
            stdout=out,
        )
        output = out.getvalue()
        self.assertIn("succeeded", output)
        # A job now exists and its state is queryable via the CLI status path.
        job = models.PipelineJob.objects.latest("created_at")
        status_out = StringIO()
        call_command("run_pipeline", f"--status={job.pk}", stdout=status_out)
        self.assertIn("generate_reports", status_out.getvalue())
