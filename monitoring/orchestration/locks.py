"""Resource lock operations for SQLite-backed dashboard workers."""

from datetime import timedelta

from django.db import IntegrityError
from django.utils import timezone

from monitoring.dashboard_models import PipelineJob
from monitoring.orchestration_models import ResourceLock


def acquire_lock(
    resource_name: str,
    job: PipelineJob,
    ttl_seconds: int,
    worker_id: str = "worker",
) -> ResourceLock | None:
    """Acquire a named resource lock or return None if unavailable.

    Example:
        `lock = acquire_lock("gpu:0", job, 120, "gpu-1")`
    """
    cleanup_expired_locks()
    if ResourceLock.objects.filter(resource_name=resource_name).exists():
        return None
    expires_at = timezone.now() + timedelta(seconds=ttl_seconds)
    try:
        return ResourceLock.objects.create(
            resource_name=resource_name,
            locked_by_worker=worker_id,
            job=job,
            expires_at=expires_at,
        )
    except IntegrityError:
        return None


def refresh_lock(lock: ResourceLock, ttl_seconds: int = 120) -> ResourceLock:
    """Extend one resource lock heartbeat and expiry.

    Example:
        `refresh_lock(lock)`
    """
    lock.heartbeat_at = timezone.now()
    lock.expires_at = lock.heartbeat_at + timedelta(seconds=ttl_seconds)
    lock.save(update_fields=["heartbeat_at", "expires_at"])
    return lock


def release_lock(lock: ResourceLock | None) -> None:
    """Release a lock if it still exists.

    Example:
        `release_lock(lock)`
    """
    if lock is None:
        return
    ResourceLock.objects.filter(pk=lock.pk).delete()


def cleanup_expired_locks() -> int:
    """Delete expired resource locks and return the number removed.

    Example:
        `removed = cleanup_expired_locks()`
    """
    deleted_count, _details = ResourceLock.objects.filter(
        expires_at__lt=timezone.now()
    ).delete()
    return deleted_count
