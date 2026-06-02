"""Local synchronous compute provider."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from dataclasses import dataclass, field

from src.providers.base import JobSubmission


@dataclass(slots=True)
class LocalComputeProvider:
    """Run compute jobs as local completed submissions.

    Example:
        `LocalComputeProvider().submit_job({"name": "risk"})`
    """

    _jobs: dict[str, JobSubmission] = field(default_factory=dict)

    def submit_job(self, job_spec: Mapping[str, object]) -> JobSubmission:
        """Submit a local job and mark it completed."""
        job_id = _job_id(job_spec)
        result = JobSubmission(job_id, "COMPLETED", {"provider": "local"})
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


def _job_id(job_spec: Mapping[str, object]) -> str:
    payload = json.dumps(dict(job_spec), sort_keys=True, default=str)
    digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()
    return f"local-{digest[:16]}"
