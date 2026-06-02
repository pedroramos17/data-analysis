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
        """Submit a compute job."""

    def get_status(self, job_id: str) -> JobSubmission:
        """Return the current job status."""

    def cancel(self, job_id: str) -> JobSubmission:
        """Cancel a job if the provider supports cancellation."""
