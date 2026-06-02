"""SQLite-backed orchestration state for dashboard workers."""

from django.db import models
from django.utils import timezone

from monitoring.dashboard_models import PipelineJob


class ResourceLock(models.Model):
    """A short-lived lock for a CPU, GPU, or cloud execution slot.

    Example:
        `ResourceLock.objects.filter(resource_name="gpu:0").exists()`
    """

    resource_name = models.CharField(max_length=120, unique=True)
    locked_by_worker = models.CharField(max_length=150)
    job = models.ForeignKey(
        PipelineJob,
        null=True,
        blank=True,
        related_name="resource_locks",
        on_delete=models.SET_NULL,
    )
    expires_at = models.DateTimeField()
    created_at = models.DateTimeField(auto_now_add=True)
    heartbeat_at = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ["resource_name"]
        indexes = [
            models.Index(fields=["expires_at"], name="orch_lock_expires_idx"),
            models.Index(fields=["locked_by_worker"], name="orch_lock_worker_idx"),
            models.Index(fields=["job"], name="orch_lock_job_idx"),
        ]

    def __str__(self) -> str:
        """Return a compact lock label.

        Example:
            `str(lock)` returns `gpu:0 by worker-1`.
        """
        return f"{self.resource_name} by {self.locked_by_worker}"


class WorkerHeartbeat(models.Model):
    """Latest heartbeat emitted by a dashboard worker process.

    Example:
        `WorkerHeartbeat.objects.filter(status="running")`
    """

    class Status(models.TextChoices):
        STARTING = "starting", "Starting"
        IDLE = "idle", "Idle"
        RUNNING = "running", "Running"
        STOPPED = "stopped", "Stopped"
        ERROR = "error", "Error"
        STALE = "stale", "Stale"

    worker_id = models.CharField(max_length=150, unique=True)
    hostname = models.CharField(max_length=255)
    profile = models.CharField(max_length=40)
    backend = models.CharField(max_length=20, default="auto")
    status = models.CharField(
        max_length=32,
        choices=Status.choices,
        default=Status.STARTING,
    )
    pid = models.PositiveIntegerField(default=0)
    current_job = models.ForeignKey(
        PipelineJob,
        null=True,
        blank=True,
        related_name="worker_heartbeats",
        on_delete=models.SET_NULL,
    )
    started_at = models.DateTimeField(default=timezone.now)
    last_heartbeat_at = models.DateTimeField(default=timezone.now)
    metadata_json = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ["worker_id"]
        indexes = [
            models.Index(fields=["profile", "status"], name="orch_worker_profile_idx"),
            models.Index(
                fields=["last_heartbeat_at"],
                name="orch_worker_heartbeat_idx",
            ),
            models.Index(fields=["current_job"], name="orch_worker_job_idx"),
        ]

    def __str__(self) -> str:
        """Return the worker id.

        Example:
            `str(worker)` returns `cpu-1`.
        """
        return self.worker_id
