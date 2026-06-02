"""SQLite-backed scheduler operations for dashboard workers."""

from collections.abc import Mapping
from decimal import Decimal

from django.db import transaction
from django.utils import timezone

from monitoring.compute.profiles import list_compute_profiles
from monitoring.compute.routing import validate_task_allowed
from monitoring.compute.task_registry import TASK_REGISTRY
from monitoring.dashboard_models import ComputeProfileConfig, PipelineJob
from monitoring.orchestration.command_validation import validate_management_command
from monitoring.orchestration.logging import append_job_event
from monitoring.orchestration.profile_config import sync_default_profile_configs
from monitoring.orchestration.resources import acquire_job_lock
from monitoring.orchestration_models import ResourceLock


TERMINAL_STATUSES = {"failed", "cancelled", "succeeded"}


def enqueue_job(
    task_name: str,
    profile: str | ComputeProfileConfig,
    backend: str,
    params: Mapping[str, object],
) -> PipelineJob:
    """Create a queued pipeline job after validating task and command.

    Example:
        `enqueue_job("export_parquet", "local_cpu_low", "cpu", {"command": "..."})`
    """
    profile_config = _profile_config(profile)
    _validate_task_name(task_name)
    validate_task_allowed(task_name, profile_config.profile_type)
    command = str(params.get("command", ""))
    if command:
        validate_management_command(command)
    job = PipelineJob.objects.create(
        job_name=str(params.get("job_name", task_name)),
        task_name=task_name,
        profile=profile_config,
        backend=backend,
        status=PipelineJob.Status.QUEUED,
        priority=int(params.get("priority", 100)),
        command=command,
        parameters_json=dict(params),
        estimated_cost_usd=Decimal(str(params.get("estimated_cost_usd", "0"))),
        estimated_runtime_seconds=int(params.get("estimated_runtime_seconds", 0)),
    )
    append_job_event(job, "created", "Job created from dashboard scheduler")
    append_job_event(job, "queued", "Job queued")
    return job


def claim_next_job(worker_id: str, profile: str) -> tuple[PipelineJob, ResourceLock] | None:
    """Atomically claim the next queued local job for a worker.

    Example:
        `claimed = claim_next_job("cpu-1", "local_cpu_low")`
    """
    sync_default_profile_configs()
    for job in _candidate_jobs(profile):
        if not _resource_policy_allows(job):
            _mark_waiting_resource(job)
            continue
        lock = acquire_job_lock(job, worker_id)
        if lock is None:
            continue
        if _mark_running(job):
            job.refresh_from_db()
            append_job_event(job, "started", f"Claimed by {worker_id}")
            return job, lock
        ResourceLock.objects.filter(pk=lock.pk).delete()
    return None


def cancel_job(job_id: int) -> PipelineJob:
    """Cancel a queued or running job.

    Example:
        `cancel_job(123)`
    """
    return _set_job_status(job_id, PipelineJob.Status.CANCELLED, "cancelled")


def pause_job(job_id: int) -> PipelineJob:
    """Pause a queued or running job cooperatively.

    Example:
        `pause_job(123)`
    """
    return _set_job_status(job_id, PipelineJob.Status.PAUSED, "paused")


def resume_job(job_id: int) -> PipelineJob:
    """Resume a paused or resource-waiting job by re-queueing it.

    Example:
        `resume_job(123)`
    """
    return _set_job_status(job_id, PipelineJob.Status.QUEUED, "queued")


def retry_job(job_id: int) -> PipelineJob:
    """Retry a terminal job by clearing errors and re-queueing it.

    Example:
        `retry_job(123)`
    """
    job = PipelineJob.objects.get(pk=job_id)
    job.status = PipelineJob.Status.QUEUED
    job.error_message = ""
    job.progress_current = 0
    job.progress_total = 0
    job.progress_percent = 0
    job.started_at = None
    job.finished_at = None
    job.save()
    append_job_event(job, "queued", "Job retry queued")
    return job


def _candidate_jobs(profile: str) -> list[PipelineJob]:
    queryset = PipelineJob.objects.select_related("profile").filter(
        status=PipelineJob.Status.QUEUED,
        profile__enabled=True,
        profile__queue_enabled=True,
    )
    if profile != "all-local":
        queryset = queryset.filter(profile__profile_type=profile)
    ordered = queryset.exclude(backend="cloud").order_by("priority", "created_at")
    return list(ordered[:20])


def _mark_running(job: PipelineJob) -> bool:
    with transaction.atomic():
        updated = PipelineJob.objects.filter(
            pk=job.pk,
            status=PipelineJob.Status.QUEUED,
        ).update(status=PipelineJob.Status.RUNNING, started_at=timezone.now())
    return updated == 1


def _resource_policy_allows(job: PipelineJob) -> bool:
    if job.backend in ("gpu", "cuda", "cupy"):
        return job.profile.max_gpu_workers > 0 and job.profile.max_vram_gb > 0
    return job.profile.max_cpu_workers > 0


def _mark_waiting_resource(job: PipelineJob) -> None:
    PipelineJob.objects.filter(pk=job.pk, status=PipelineJob.Status.QUEUED).update(
        status=PipelineJob.Status.WAITING_RESOURCE
    )
    append_job_event(job, "resource_blocked", "Profile resource limits block job")


def _set_job_status(job_id: int, status: str, event_type: str) -> PipelineJob:
    job = PipelineJob.objects.get(pk=job_id)
    job.status = status
    if status in TERMINAL_STATUSES:
        job.finished_at = timezone.now()
    job.save(update_fields=["status", "finished_at", "updated_at"])
    append_job_event(job, event_type, f"Job marked {status}")
    return job


def _profile_config(profile: str | ComputeProfileConfig) -> ComputeProfileConfig:
    if isinstance(profile, ComputeProfileConfig):
        return profile
    sync_default_profile_configs()
    return ComputeProfileConfig.objects.get(profile_type=profile)


def _validate_task_name(task_name: str) -> None:
    known_tasks = set(TASK_REGISTRY)
    for compute_profile in list_compute_profiles():
        known_tasks.update(compute_profile.allowed_tasks)
    if task_name not in known_tasks:
        expected = ", ".join(sorted(known_tasks))
        raise ValueError(f"Invalid task {task_name!r}; expected one of: {expected}")
