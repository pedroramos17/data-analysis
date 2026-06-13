"""In-memory rate-limit provider."""

from __future__ import annotations

import time
from dataclasses import dataclass, field

from src.config.settings import RateLimitSettings
from src.providers.rate_limit.base import RateLimitDecision


@dataclass(slots=True)
class MemoryRateLimitProvider:
    """Fixed-window in-memory rate limiter for local runs and tests.

    Example:
        `MemoryRateLimitProvider(settings).allow("api")`
    """

    settings: RateLimitSettings
    _windows: dict[tuple[str, int], int] = field(default_factory=dict)

    def allow(self, key: str, cost: int = 1) -> RateLimitDecision:
        """Return whether a key remains within its current minute window."""
        now = time.time()
        window = int(now // 60)
        limit = _limit(self.settings)
        increment = max(int(cost), 1)
        counter_key = (key, window)
        used = self._windows.get(counter_key, 0) + increment
        self._windows[counter_key] = used
        return RateLimitDecision(
            allowed=used <= limit,
            limit=limit,
            remaining=max(limit - used, 0),
            reset_after_seconds=_reset_after_seconds(now),
            provider="memory",
        )

    def reset(self, key: str) -> None:
        """Reset all in-memory counters for a key."""
        for counter_key in list(self._windows):
            if counter_key[0] == key:
                del self._windows[counter_key]

    def healthcheck(self) -> bool:
        """Return whether memory rate limiting is usable."""
        return True


def _limit(settings: RateLimitSettings) -> int:
    return max(settings.requests_per_minute + settings.burst, 1)


def _reset_after_seconds(now: float) -> int:
    return max(60 - int(now % 60), 1)
