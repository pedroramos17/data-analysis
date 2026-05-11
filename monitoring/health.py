"""Feed health and circuit-breaker helpers."""

from datetime import datetime, timedelta

from django.utils import timezone

from monitoring.models import IngestionCheckpoint, Source

FAILURE_COOLDOWN_MINUTES = 5
FAILURE_THRESHOLD = 2


def source_is_in_cooldown(source: Source) -> bool:
    """Return whether a source is currently circuit-broken.

    Example:
        `source_is_in_cooldown(source)`
    """
    checkpoint = IngestionCheckpoint.objects.filter(source=source).first()
    if checkpoint is None or checkpoint.cooldown_until is None:
        return False
    return checkpoint.cooldown_until > timezone.now()


def record_checkpoint_failure(source: Source, error: Exception) -> None:
    """Update checkpoint failure state and enter cooldown when needed.

    Example:
        `record_checkpoint_failure(source, error)`
    """
    checkpoint, _created = IngestionCheckpoint.objects.get_or_create(source=source)
    checkpoint.last_attempt_at = timezone.now()
    checkpoint.last_status = "failed"
    checkpoint.error_message = str(error)
    checkpoint.last_error_type = type(error).__name__
    checkpoint.consecutive_failures += 1
    checkpoint.cooldown_until = _next_cooldown(checkpoint.consecutive_failures)
    checkpoint.save(update_fields=_failure_fields())


def record_checkpoint_success(
    source: Source,
    item_count: int,
    last_http_status: int | None,
) -> None:
    """Clear failure state after a successful source run.

    Example:
        `record_checkpoint_success(source, 10, 200)`
    """
    checkpoint, _created = IngestionCheckpoint.objects.get_or_create(source=source)
    checkpoint.last_attempt_at = timezone.now()
    checkpoint.last_success_at = checkpoint.last_attempt_at
    checkpoint.last_status = "succeeded"
    checkpoint.item_count = item_count
    checkpoint.error_message = ""
    checkpoint.consecutive_failures = 0
    checkpoint.cooldown_until = None
    checkpoint.last_http_status = last_http_status
    checkpoint.last_error_type = ""
    checkpoint.save(update_fields=_success_fields())


def _next_cooldown(consecutive_failures: int) -> datetime | None:
    if consecutive_failures < FAILURE_THRESHOLD:
        return None
    return timezone.now() + timedelta(minutes=FAILURE_COOLDOWN_MINUTES)


def _failure_fields() -> list[str]:
    return [
        "last_attempt_at",
        "last_status",
        "error_message",
        "last_error_type",
        "consecutive_failures",
        "cooldown_until",
    ]


def _success_fields() -> list[str]:
    return [
        "last_attempt_at",
        "last_success_at",
        "last_status",
        "item_count",
        "error_message",
        "consecutive_failures",
        "cooldown_until",
        "last_http_status",
        "last_error_type",
    ]
