"""Local synchronous compute provider."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field

from src.providers.base import JobSubmission

LocalJobRunner = Callable[[Mapping[str, object]], object]
RUNNER_KEYS = frozenset({"callable", "handler", "runner"})


@dataclass(slots=True)
class LocalComputeProvider:
    """Run explicit compute jobs synchronously on the local process.

    Example:
        `LocalComputeProvider().submit_job({"name": "risk", "handler": run})`
    """

    _jobs: dict[str, JobSubmission] = field(default_factory=dict)

    def submit_job(self, job_spec: Mapping[str, object]) -> JobSubmission:
        """Run a local callable when supplied and record its final status."""
        job_id = _job_id(job_spec)
        metadata = {"provider": "local", "job_spec": _safe_job_spec(job_spec)}
        runner = _runner(job_spec)
        if runner is None:
            result = JobSubmission(
                job_id,
                "PLANNED",
                metadata | {"reason": "no local runner supplied"},
            )
            self._jobs[job_id] = result
            return result

        try:
            output = runner(_payload(job_spec))
        except Exception as exc:
            result = JobSubmission(
                job_id,
                "FAILED",
                metadata
                | {"error": {"type": type(exc).__name__, "message": str(exc)}},
            )
        else:
            result = JobSubmission(job_id, "COMPLETED", metadata | {"result": output})
        self._jobs[job_id] = result
        return result

    def get_status(self, job_id: str) -> JobSubmission:
        """Return a local job status."""
        return self._jobs.get(job_id, JobSubmission(job_id, "UNKNOWN", {}))

    def cancel(self, job_id: str) -> JobSubmission:
        """Mark a local job as cancelled."""
        result = JobSubmission(job_id, "CANCELLED", {"provider": "local"})
        self._jobs[job_id] = result
        return result

    def cancel_job(self, job_id: str) -> JobSubmission:
        """Phase 2 alias for `cancel`."""
        return self.cancel(job_id)

    def stream_logs(self, job_id: str) -> list[str]:
        """Return local job log lines when present."""
        submission = self.get_status(job_id)
        logs = submission.metadata.get("logs", [])
        if isinstance(logs, list):
            return [str(line) for line in logs]
        return []

    def terminate_idle(self) -> dict[str, object]:
        """Local compute has no remote idle resources to terminate."""
        return {"provider": "local", "terminated": 0}

    def estimate_cost(self, job_spec: Mapping[str, object]) -> dict[str, object]:
        """Local compute is free for budget accounting."""
        return {"provider": "local", "estimated_cost_usd": 0.0, "currency": "USD"}

    def healthcheck(self) -> bool:
        """Return whether local compute can accept jobs."""
        return True


def _job_id(job_spec: Mapping[str, object]) -> str:
    payload = json.dumps(_safe_job_spec(job_spec), sort_keys=True, default=str)
    digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()
    return f"local-{digest[:16]}"


def _runner(job_spec: Mapping[str, object]) -> LocalJobRunner | None:
    for key in RUNNER_KEYS:
        candidate = job_spec.get(key)
        if callable(candidate):
            return candidate
    return None


def _payload(job_spec: Mapping[str, object]) -> Mapping[str, object]:
    payload = job_spec.get("payload", {})
    if isinstance(payload, Mapping):
        return payload
    return {"value": payload}


def _safe_job_spec(job_spec: Mapping[str, object]) -> dict[str, object]:
    return {
        key: value
        for key, value in job_spec.items()
        if key not in RUNNER_KEYS and not callable(value)
    }
