"""Worker heartbeat state helpers."""

from datetime import timedelta
import os
import socket

from django.utils import timezone

from monitoring.dashboard_models import PipelineJob
from monitoring.orchestration_models import WorkerHeartbeat


def register_worker(
    worker_id: str,
    profile: str,
    backend: str = "auto",
) -> WorkerHeartbeat:
    """Create or refresh a worker heartbeat row.

    Example:
        `register_worker("cpu-1", "local_cpu_low")`
    """
    now = timezone.now()
    worker, _created = WorkerHeartbeat.objects.update_or_create(
        worker_id=worker_id,
        defaults={
            "hostname": socket.gethostname(),
            "profile": profile,
            "backend": backend,
            "status": WorkerHeartbeat.Status.IDLE,
            "pid": os.getpid(),
            "started_at": now,
            "last_heartbeat_at": now,
            "current_job": None,
        },
    )
    return worker


def heartbeat_worker(
    worker_id: str,
    status: str,
    current_job: PipelineJob | None = None,
    metadata: dict[str, object] | None = None,
) -> WorkerHeartbeat:
    """Update heartbeat status and current job for a worker.

    Example:
        `heartbeat_worker("cpu-1", "running", job)`
    """
    worker = WorkerHeartbeat.objects.get(worker_id=worker_id)
    worker.status = status
    worker.current_job = current_job
    worker.last_heartbeat_at = timezone.now()
    worker.metadata_json = metadata or worker.metadata_json
    worker.save(
        update_fields=[
            "status",
            "current_job",
            "last_heartbeat_at",
            "metadata_json",
        ]
    )
    return worker


def stop_worker(worker_id: str) -> WorkerHeartbeat:
    """Mark a worker stopped after a clean exit.

    Example:
        `stop_worker("cpu-1")`
    """
    worker = WorkerHeartbeat.objects.get(worker_id=worker_id)
    worker.status = WorkerHeartbeat.Status.STOPPED
    worker.current_job = None
    worker.last_heartbeat_at = timezone.now()
    worker.save(update_fields=["status", "current_job", "last_heartbeat_at"])
    return worker


def mark_stale_workers(ttl_seconds: int = 120) -> int:
    """Mark old non-stopped worker heartbeats as stale.

    Example:
        `mark_stale_workers(300)`
    """
    cutoff = timezone.now() - timedelta(seconds=ttl_seconds)
    queryset = WorkerHeartbeat.objects.exclude(status=WorkerHeartbeat.Status.STOPPED)
    return queryset.filter(last_heartbeat_at__lt=cutoff).update(
        status=WorkerHeartbeat.Status.STALE
    )


def stop_stale_workers() -> int:
    """Mark stale workers as stopped from the dashboard.

    Example:
        `stop_stale_workers()`
    """
    return WorkerHeartbeat.objects.filter(
        status=WorkerHeartbeat.Status.STALE
    ).update(status=WorkerHeartbeat.Status.STOPPED)
