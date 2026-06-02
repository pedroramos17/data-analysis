"""Shared provider exceptions and status payloads."""

from __future__ import annotations

from dataclasses import dataclass


class ProviderError(RuntimeError):
    """Base provider failure with actionable runtime context.

    Example:
        `raise ProviderError("Invalid storage path")`
    """


class MissingProviderDependencyError(ProviderError):
    """Raised when an optional provider dependency is not installed.

    Example:
        `raise MissingProviderDependencyError("boto3 is required")`
    """


@dataclass(frozen=True, slots=True)
class JobSubmission:
    """Provider-neutral compute job submission result.

    Example:
        `JobSubmission("job-1", "COMPLETED", {})`
    """

    job_id: str
    status: str
    metadata: dict[str, object]
