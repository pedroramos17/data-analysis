"""Job submission helpers for API endpoints."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import asdict

from src.providers.registry import ProviderRegistry

ApiJobHandler = Callable[[Mapping[str, object]], Mapping[str, object]]


def submit_api_job(
    registry: ProviderRegistry,
    name: str,
    payload: Mapping[str, object] | None = None,
    *,
    sync: bool = False,
    handler: ApiJobHandler | None = None,
) -> dict[str, object]:
    """Submit an API job via provider facades.

    Local synchronous execution only happens when `sync=True`, the configured
    compute provider is local, and a real handler is supplied. Otherwise the job
    is published to the configured queue and submitted as a manifest.
    """
    job_payload = dict(payload or {})
    if sync and handler is not None and registry.settings.compute.provider == "local":
        submission = registry.get_compute().submit_job(
            {"name": name, "payload": job_payload, "handler": handler}
        )
        return _submission_payload(submission, queued=False)

    message_id = registry.get_queue().publish(name, job_payload)
    submission = registry.get_compute().submit_job(
        {"name": name, "payload": job_payload, "queue_message_id": message_id}
    )
    return _submission_payload(submission, queued=True) | {"queue_message_id": message_id}


def _submission_payload(submission: object, *, queued: bool) -> dict[str, object]:
    if hasattr(submission, "__dataclass_fields__"):
        payload = asdict(submission)
    else:
        payload = {
            "job_id": getattr(submission, "job_id", ""),
            "status": getattr(submission, "status", "UNKNOWN"),
            "metadata": getattr(submission, "metadata", {}),
        }
    return {
        "job_id": str(payload.get("job_id", "")),
        "status": str(payload.get("status", "UNKNOWN")),
        "queued": queued,
        "metadata": _json_safe(payload.get("metadata", {})),
    }


def _json_safe(value: object) -> object:
    if isinstance(value, Mapping):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, list | tuple):
        return [_json_safe(item) for item in value]
    if isinstance(value, str | int | float | bool) or value is None:
        return value
    return str(value)
