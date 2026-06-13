"""Batch compute provider stubs for optional cloud/GPU execution."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from dataclasses import dataclass, field

from src.providers.base import JobSubmission, ProviderError


@dataclass(slots=True)
class BatchStubComputeProvider:
    """Manifest-only compute provider for future batch integrations.

    Example:
        `BatchStubComputeProvider("vastai").submit_job({"name": "x"})`
    """

    provider_name: str
    _jobs: dict[str, JobSubmission] = field(default_factory=dict)

    def submit_job(self, job_spec: Mapping[str, object]) -> JobSubmission:
        """Record a queued batch job manifest without executing it."""
        job_id = _batch_job_id(self.provider_name, job_spec)
        metadata = {"provider": self.provider_name, "job_spec": dict(job_spec)}
        result = JobSubmission(job_id, "QUEUED", metadata)
        self._jobs[job_id] = result
        return result

    def get_status(self, job_id: str) -> JobSubmission:
        """Return a known batch job status."""
        return self._jobs.get(job_id, JobSubmission(job_id, "UNKNOWN", {}))

    def cancel(self, job_id: str) -> JobSubmission:
        """Cancel a known batch job manifest."""
        if job_id not in self._jobs:
            raise ProviderError(f"Invalid job_id {job_id!r}; expected known job")
        result = JobSubmission(job_id, "CANCELLED", {"provider": self.provider_name})
        self._jobs[job_id] = result
        return result

    def cancel_job(self, job_id: str) -> JobSubmission:
        """Phase 2 alias for `cancel`."""
        return self.cancel(job_id)

    def stream_logs(self, job_id: str) -> list[str]:
        """Batch stubs do not have remote logs."""
        return [] if job_id in self._jobs else []

    def terminate_idle(self) -> dict[str, object]:
        """Batch stubs never launch remote resources."""
        return {"provider": self.provider_name, "terminated": 0}

    def estimate_cost(self, job_spec: Mapping[str, object]) -> dict[str, object]:
        """Return a manifest-only cost placeholder."""
        return {"provider": self.provider_name, "estimated_cost_usd": 0.0, "currency": "USD"}

    def healthcheck(self) -> bool:
        """Return whether manifest-only planning is available."""
        return True


def _batch_job_id(provider_name: str, job_spec: Mapping[str, object]) -> str:
    payload = json.dumps(dict(job_spec), sort_keys=True, default=str)
    digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()
    return f"{provider_name}-{digest[:16]}"
