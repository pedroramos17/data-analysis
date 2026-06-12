"""The sourceflow pipeline runner.

Creates a :class:`PipelineJob` with one :class:`PipelineStageRun` per stage, then
executes stages in order (or one at a time), persisting state at each step so a
job's progress is always visible in the database. Each stage execution is
rate-limited, retried up to its policy, and logged with the document id and the
model/extractor versions it used.
"""

from __future__ import annotations

import logging
import time

from sourceflow.orchestration.policies import RateLimitPolicy, RetryPolicy
from sourceflow.orchestration.stages import STAGE_ORDER, STAGES, PipelineContext

logger = logging.getLogger("sourceflow.orchestration")


class PipelineRunner:
    def __init__(
        self,
        *,
        retry_policy: RetryPolicy | None = None,
        rate_limiter: RateLimitPolicy | None = None,
    ) -> None:
        self.retry_policy = retry_policy or RetryPolicy()
        self.rate_limiter = rate_limiter or RateLimitPolicy()

    # -- job lifecycle ------------------------------------------------------

    def create_job(self, payload: dict | None = None, *, document=None,
                   pipeline_name: str = "sourceflow_document_pipeline"):
        from sourceflow.models import PipelineJob, PipelineStageRun

        job = PipelineJob.objects.create(
            pipeline_name=pipeline_name,
            params_json=dict(payload or {}),
            document=document,
        )
        for sequence, name in enumerate(STAGE_ORDER):
            PipelineStageRun.objects.create(
                job=job,
                stage_name=name,
                sequence=sequence,
                status=PipelineStageRun.Status.PENDING,
                max_attempts=self.retry_policy.attempts_for(name),
            )
        return job

    def run(self, job, *, stages: list[str] | None = None):
        """Run the pipeline (or a subset of stages) in order, stopping on failure."""
        from django.utils import timezone
        from sourceflow.models import PipelineJob, PipelineStageRun

        names = stages or STAGE_ORDER
        job.status = PipelineJob.Status.RUNNING
        job.started_at = job.started_at or timezone.now()
        job.save(update_fields=["status", "started_at", "updated_at"])

        context = self._context(job)
        for name in names:
            stage_run = self._execute_stage(job, name, context)
            if stage_run.status == PipelineStageRun.Status.FAILED:
                break  # a failed stage halts the run; it stays retryable
        self._finalize_job_status(job)
        return job

    def run_stage(self, job, stage_name: str):
        """Run a single stage independently (its own fresh context)."""
        if stage_name not in STAGES:
            raise ValueError(f"unknown stage: {stage_name!r}")
        stage_run = self._execute_stage(job, stage_name, self._context(job))
        self._finalize_job_status(job)
        return stage_run

    def retry_stage(self, job, stage_name: str):
        """Reset a stage to pending and run it again."""
        from sourceflow.models import PipelineStageRun

        stage_run = PipelineStageRun.objects.get(job=job, stage_name=stage_name)
        stage_run.status = PipelineStageRun.Status.PENDING
        stage_run.error = ""
        stage_run.save(update_fields=["status", "error", "updated_at"])
        return self.run_stage(job, stage_name)

    # -- internals ----------------------------------------------------------

    def _context(self, job) -> PipelineContext:
        return PipelineContext(job=job, payload=dict(job.params_json or {}), document_id=job.document_id)

    def _execute_stage(self, job, name: str, context: PipelineContext):
        from django.utils import timezone
        from sourceflow.models import PipelineStageRun

        stage_fn = STAGES[name]
        stage_run = PipelineStageRun.objects.get(job=job, stage_name=name)
        attempts_allowed = stage_run.max_attempts or self.retry_policy.attempts_for(name)

        # Rate-limit each stage execution (generous defaults never block).
        self.rate_limiter.acquire()

        stage_run.status = PipelineStageRun.Status.RUNNING
        stage_run.started_at = timezone.now()
        stage_run.save(update_fields=["status", "started_at", "updated_at"])

        last_error = ""
        for attempt in range(1, attempts_allowed + 1):
            backoff = self.retry_policy.backoff_for(attempt)
            if backoff > 0:
                time.sleep(backoff)
            stage_run.attempts = attempt
            try:
                result = stage_fn(context)
            except Exception as exc:  # noqa: BLE001 - recorded as stage failure
                last_error = f"{type(exc).__name__}: {exc}"
                logger.warning(
                    "sourceflow.orchestration stage_error job=%s stage=%s document_id=%s attempt=%s/%s error=%s",
                    job.pk, name, context.document_id, attempt, attempts_allowed, last_error,
                )
                continue
            stage_run.status = PipelineStageRun.Status.SUCCEEDED
            stage_run.output_json = result.output
            stage_run.model_versions_json = result.model_versions
            stage_run.error = ""
            stage_run.finished_at = timezone.now()
            stage_run.save()
            logger.info(
                "sourceflow.orchestration stage_ok job=%s stage=%s document_id=%s model_versions=%s attempt=%s",
                job.pk, name, context.document_id, result.model_versions, attempt,
            )
            return stage_run

        stage_run.status = PipelineStageRun.Status.FAILED
        stage_run.error = last_error
        stage_run.finished_at = timezone.now()
        stage_run.save()
        logger.error(
            "sourceflow.orchestration stage_failed job=%s stage=%s document_id=%s attempts=%s error=%s",
            job.pk, name, context.document_id, stage_run.attempts, last_error,
        )
        return stage_run

    def _finalize_job_status(self, job) -> None:
        from django.utils import timezone
        from sourceflow.models import PipelineJob, PipelineStageRun

        status_values = list(job.stage_runs.values_list("status", flat=True))
        S = PipelineStageRun.Status
        if any(value == S.FAILED for value in status_values):
            job.status = PipelineJob.Status.FAILED
        elif status_values and all(value == S.SUCCEEDED for value in status_values):
            job.status = PipelineJob.Status.SUCCEEDED
        elif any(value == S.SUCCEEDED for value in status_values):
            job.status = PipelineJob.Status.PARTIAL
        else:
            job.status = PipelineJob.Status.PENDING
        if job.status in (PipelineJob.Status.SUCCEEDED, PipelineJob.Status.FAILED):
            job.finished_at = job.finished_at or timezone.now()
        job.save(update_fields=["status", "finished_at", "updated_at"])


def job_state(job) -> dict:
    """Return a JSON-able snapshot of a job and its stage runs (visible state)."""
    return {
        "job_id": job.pk,
        "pipeline_name": job.pipeline_name,
        "status": job.status,
        "document_id": job.document_id,
        "report": dict(job.report_json or {}),
        "stages": [
            {
                "stage": run.stage_name,
                "sequence": run.sequence,
                "status": run.status,
                "attempts": run.attempts,
                "max_attempts": run.max_attempts,
                "model_versions": dict(run.model_versions_json or {}),
                "output": dict(run.output_json or {}),
                "error": run.error,
            }
            for run in job.stage_runs.all()
        ],
    }
