"""Generic dry-run compute provider."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from dataclasses import dataclass, field

from src.providers.base import JobSubmission


@dataclass(slots=True)
class DryRunComputeProvider:
    """Record compute specs without executing local or remote work.

    Example:
        `DryRunComputeProvider().submit_job({"name": "train"})`
    """

    provider_name: str = "stub"
    _jobs: dict[str, JobSubmission] = field(default_factory=dict)

    def submit_job(self, job_spec: Mapping[str, object]) -> JobSubmission:
        """Record a planned dry-run job manifest."""
        job_id = _dry_run_job_id(self.provider_name, job_spec)
        result = JobSubmission(
            job_id,
            "PLANNED",
            {
                "provider": self.provider_name,
                "dry_run": True,
                "job_spec": dict(job_spec),
                "launches_paid_infrastructure": False,
            },
        )
        self._jobs[job_id] = result
        return result

    def get_status(self, job_id: str) -> JobSubmission:
        """Return a known dry-run job status."""
        return self._jobs.get(job_id, JobSubmission(job_id, "UNKNOWN", {}))

    def stream_logs(self, job_id: str) -> list[str]:
        """Dry-run jobs do not have remote logs."""
        return []

    def cancel(self, job_id: str) -> JobSubmission:
        """Cancel a dry-run job."""
        result = JobSubmission(job_id, "CANCELLED", {"provider": self.provider_name})
        self._jobs[job_id] = result
        return result

    def cancel_job(self, job_id: str) -> JobSubmission:
        """Phase 2 alias for `cancel`."""
        return self.cancel(job_id)

    def terminate_idle(self) -> dict[str, object]:
        """Dry-run jobs never launch idle resources."""
        return {"provider": self.provider_name, "terminated": 0}

    def estimate_cost(self, job_spec: Mapping[str, object]) -> dict[str, object]:
        """Dry-run planning is free."""
        return {"provider": self.provider_name, "estimated_cost_usd": 0.0, "currency": "USD"}

    def healthcheck(self) -> bool:
        """Return whether dry-run planning is available."""
        return True


def _dry_run_job_id(provider_name: str, job_spec: Mapping[str, object]) -> str:
    payload = json.dumps(dict(job_spec), sort_keys=True, default=str)
    digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()
    return f"{provider_name}-dryrun-{digest[:16]}"
