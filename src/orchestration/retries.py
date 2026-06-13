"""Retry policy helpers for orchestrated tasks."""

from __future__ import annotations

import time
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class RetryPolicy:
    """Simple bounded retry policy."""

    max_attempts: int = 2
    backoff_seconds: float = 0.0

    @property
    def max_retries(self) -> int:
        """Return retry count after the first attempt."""
        return max(self.max_attempts - 1, 0)

    def should_retry(self, attempt: int) -> bool:
        """Return whether another attempt is allowed."""
        return attempt < self.max_attempts

    def sleep_before_retry(self, attempt: int) -> None:
        """Sleep before retrying, using linear backoff."""
        delay = max(self.backoff_seconds, 0.0) * max(attempt, 1)
        if delay > 0:
            time.sleep(delay)


def retry_policy_from_config(config: object) -> RetryPolicy:
    """Build retry policy from a config mapping."""
    if not isinstance(config, dict):
        return RetryPolicy()
    retry_config = config.get("retries", {})
    if not isinstance(retry_config, dict):
        return RetryPolicy()
    return RetryPolicy(
        max_attempts=int(retry_config.get("max_attempts", 2)),
        backoff_seconds=float(retry_config.get("backoff_seconds", 0.0)),
    )
