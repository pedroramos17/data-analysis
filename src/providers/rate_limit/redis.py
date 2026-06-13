"""Redis-backed rate-limit provider."""

from __future__ import annotations

import time
from dataclasses import dataclass

from src.config.settings import RateLimitSettings
from src.providers.base import MissingProviderDependencyError, ProviderError
from src.providers.rate_limit.base import RateLimitDecision


@dataclass(frozen=True, slots=True)
class RedisRateLimitProvider:
    """Fixed-window Redis rate limiter for shared workers.

    Example:
        `RedisRateLimitProvider(settings).allow("api")`
    """

    settings: RateLimitSettings

    def allow(self, key: str, cost: int = 1) -> RateLimitDecision:
        """Return whether a key remains within its current minute window."""
        now = time.time()
        window = int(now // 60)
        limit = _limit(self.settings)
        increment = max(int(cost), 1)
        redis_key = _counter_key(key, window)
        client = self._client()
        used = int(client.incrby(redis_key, increment))
        if used == increment:
            client.expire(redis_key, 61)
        return RateLimitDecision(
            allowed=used <= limit,
            limit=limit,
            remaining=max(limit - used, 0),
            reset_after_seconds=_reset_after_seconds(now),
            provider="redis",
        )

    def reset(self, key: str) -> None:
        """Reset the current Redis counter for a key."""
        window = int(time.time() // 60)
        self._client().delete(_counter_key(key, window))

    def healthcheck(self) -> bool:
        """Return whether Redis responds to ping."""
        return bool(self._client().ping())

    def _client(self) -> object:
        if not self.settings.redis_url:
            raise ProviderError(
                "RATE_LIMIT_REDIS_URL or REDIS_URL is required when "
                "RATE_LIMIT_PROVIDER=redis"
            )
        redis = _redis_module()
        return redis.Redis.from_url(self.settings.redis_url)


def _redis_module() -> object:
    try:
        import redis
    except ImportError as exc:
        raise MissingProviderDependencyError(
            "redis is required by Redis rate-limit provider; expected installed module"
        ) from exc
    return redis


def _limit(settings: RateLimitSettings) -> int:
    return max(settings.requests_per_minute + settings.burst, 1)


def _counter_key(key: str, window: int) -> str:
    return f"rate_limit:{key}:{window}"


def _reset_after_seconds(now: float) -> int:
    return max(60 - int(now % 60), 1)
