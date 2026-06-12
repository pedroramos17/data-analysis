"""Retry and rate-limit policies for the sourceflow pipeline runner.

Both policies are dependency-light and deterministic (the rate limiter takes an
injectable clock) so they can be unit-tested without real time or sleeps.
"""

from __future__ import annotations

import time
from dataclasses import dataclass


class RateLimitExceeded(RuntimeError):
    """Raised when a non-blocking rate-limit acquire has no tokens available."""

    def __init__(self, retry_after: float) -> None:
        super().__init__(f"rate limit exceeded; retry after {retry_after:.3f}s")
        self.retry_after = retry_after


@dataclass(frozen=True)
class RetryPolicy:
    """How many times a failed stage may be attempted, and the backoff between."""

    max_attempts: int = 2
    backoff_seconds: float = 0.0
    backoff_multiplier: float = 2.0

    def attempts_for(self, stage_name: str) -> int:
        return max(1, self.max_attempts)

    def backoff_for(self, attempt: int) -> float:
        """Backoff before the given (1-based) attempt; 0 for the first try."""
        if attempt <= 1 or self.backoff_seconds <= 0:
            return 0.0
        return self.backoff_seconds * (self.backoff_multiplier ** (attempt - 2))


class RateLimitPolicy:
    """Token-bucket rate limiter.

    ``capacity`` tokens refill at ``refill_rate`` tokens/second. Each stage
    execution costs one token. Defaults are generous so normal runs never wait;
    a tight policy (e.g. capacity=1, refill_rate=0.01) is used in tests to prove
    throttling works without sleeping.
    """

    def __init__(
        self,
        capacity: float = 1000.0,
        refill_rate: float = 1000.0,
        *,
        clock=time.monotonic,
        sleep=time.sleep,
    ) -> None:
        self.capacity = float(capacity)
        self.refill_rate = float(refill_rate)
        self._tokens = float(capacity)
        self._clock = clock
        self._sleep = sleep
        self._last = clock()

    def _refill(self) -> None:
        now = self._clock()
        elapsed = max(0.0, now - self._last)
        self._tokens = min(self.capacity, self._tokens + elapsed * self.refill_rate)
        self._last = now

    def _retry_after(self) -> float:
        if self.refill_rate <= 0:
            return float("inf")
        return max(0.0, (1.0 - self._tokens) / self.refill_rate)

    def try_acquire(self, cost: float = 1.0) -> bool:
        """Consume a token if available; return False without waiting otherwise."""
        self._refill()
        if self._tokens >= cost:
            self._tokens -= cost
            return True
        return False

    def acquire(self, cost: float = 1.0, *, block: bool = True) -> None:
        """Consume a token, waiting if necessary.

        With ``block=False`` raises :class:`RateLimitExceeded` instead of waiting.
        """
        if self.try_acquire(cost):
            return
        retry_after = self._retry_after()
        if not block:
            raise RateLimitExceeded(retry_after)
        if retry_after and retry_after != float("inf"):
            self._sleep(retry_after)
        self._refill()
        self._tokens = max(0.0, self._tokens - cost)
