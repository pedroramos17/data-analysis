"""Compute provider interface."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Protocol

from src.providers.base import JobSubmission


class ComputeProvider(Protocol):
    """Compute job boundary for local and batch execution.

    Example:
        `compute.submit_job({"name": "risk"})`
    """

    def submit_job(self, job_spec: Mapping[str, object]) -> JobSubmission:
        """Submit a compute job and return provider-neutral job metadata."""

    def get_status(self, job_id: str) -> JobSubmission:
        """Return the current job status."""

    def stream_logs(self, job_id: str) -> list[str]:
        """Return available job log lines."""

    def cancel(self, job_id: str) -> JobSubmission:
        """Cancel a job if the provider supports cancellation."""

    def cancel_job(self, job_id: str) -> JobSubmission:
        """Cancel a job using the Phase 2 provider contract name."""

    def terminate_idle(self) -> dict[str, object]:
        """Terminate idle remote resources or report a local no-op."""

    def estimate_cost(self, job_spec: Mapping[str, object]) -> dict[str, object]:
        """Estimate cost without contacting paid infrastructure."""

    def healthcheck(self) -> bool:
        """Return whether the compute provider is usable."""
