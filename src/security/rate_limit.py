"""API and job-submission rate-limit policies."""

from __future__ import annotations

import hashlib
import time
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Protocol

from src.config.settings import RateLimitSettings
from src.providers.base import MissingProviderDependencyError, ProviderError

MINUTE = 60
HOUR = 60 * MINUTE
DAY = 24 * HOUR


@dataclass(frozen=True, slots=True)
class RateLimitRule:
    """One fixed-window rate-limit rule."""

    name: str
    requests_per_minute: int | None = None
    requests_per_hour: int | None = None
    requests_per_day: int | None = None
    cost_sensitive: bool = False


@dataclass(frozen=True, slots=True)
class RateLimitIdentity:
    """Caller identity used for IP and principal rate limits."""

    ip_address: str = "unknown"
    user_id: str = ""
    api_key: str = ""
    authenticated: bool = False

    @property
    def principal_key(self) -> str:
        """Return a stable non-secret principal key."""
        if self.user_id:
            return f"user:{self.user_id}"
        if self.api_key:
            digest = hashlib.sha256(self.api_key.encode("utf-8")).hexdigest()[:16]
            return f"api_key:{digest}"
        return f"ip:{self.ip_address}"

    @property
    def is_authenticated(self) -> bool:
        """Return whether this identity should use authenticated limits."""
        return self.authenticated or bool(self.user_id or self.api_key)


@dataclass(frozen=True, slots=True)
class RateLimitRequest:
    """Rate-limit input for one API request or job submission."""

    path: str
    method: str = "POST"
    identity: RateLimitIdentity = field(default_factory=RateLimitIdentity)
    endpoint: str = ""
    cost: int = 1


@dataclass(frozen=True, slots=True)
class RateLimitResult:
    """Decision for one rate-limit evaluation."""

    allowed: bool
    status_code: int
    rule: str
    key: str
    limit: int
    remaining: int
    retry_after_seconds: int
    provider: str
    message: str = ""

    def headers(self) -> dict[str, str]:
        """Return HTTP rate-limit headers."""
        return {
            "Retry-After": str(self.retry_after_seconds),
            "X-RateLimit-Limit": str(self.limit),
            "X-RateLimit-Remaining": str(self.remaining),
            "X-RateLimit-Rule": self.rule,
        }

    def to_dict(self) -> dict[str, object]:
        """Return a JSON-friendly payload."""
        return {
            "allowed": self.allowed,
            "status_code": self.status_code,
            "rule": self.rule,
            "key": self.key,
            "limit": self.limit,
            "remaining": self.remaining,
            "retry_after_seconds": self.retry_after_seconds,
            "provider": self.provider,
            "message": self.message,
        }


@dataclass(frozen=True, slots=True)
class RateLimitCheck:
    """Internal fixed-window check."""

    rule_name: str
    key: str
    limit: int
    window_seconds: int
    cost: int


@dataclass(frozen=True, slots=True)
class CounterResult:
    """Store-level fixed-window counter result."""

    used: int
    limit: int
    reset_after_seconds: int
    provider: str

    @property
    def allowed(self) -> bool:
        """Return whether the counter remains within limit."""
        return self.used <= self.limit

    @property
    def remaining(self) -> int:
        """Return remaining requests in the current window."""
        return max(self.limit - self.used, 0)


class RateLimitStore(Protocol):
    """Store interface for fixed-window rate limiting."""

    provider: str

    def increment(self, key: str, window_seconds: int, limit: int, cost: int, now: float) -> CounterResult:
        """Increment a fixed-window key."""

    def reset(self, prefix: str = "") -> None:
        """Reset matching counters when supported."""


@dataclass(slots=True)
class MemoryRateLimitStore:
    """In-memory fixed-window store for local mode and tests."""

    provider: str = "memory"
    _counters: dict[tuple[str, int, int], int] = field(default_factory=dict)

    def increment(self, key: str, window_seconds: int, limit: int, cost: int, now: float) -> CounterResult:
        """Increment an in-memory fixed-window counter."""
        window = int(now // window_seconds)
        counter_key = (key, window_seconds, window)
        used = self._counters.get(counter_key, 0) + max(cost, 1)
        self._counters[counter_key] = used
        return CounterResult(
            used=used,
            limit=limit,
            reset_after_seconds=_reset_after_seconds(now, window_seconds),
            provider=self.provider,
        )

    def reset(self, prefix: str = "") -> None:
        """Reset in-memory counters by key prefix."""
        for key in list(self._counters):
            if not prefix or key[0].startswith(prefix):
                del self._counters[key]


@dataclass(frozen=True, slots=True)
class RedisRateLimitStore:
    """Redis fixed-window store for shared cloud rate limiting."""

    redis_url: str
    provider: str = "redis"

    def increment(self, key: str, window_seconds: int, limit: int, cost: int, now: float) -> CounterResult:
        """Increment a Redis fixed-window counter."""
        if not self.redis_url:
            raise ProviderError("RATE_LIMIT_REDIS_URL or REDIS_URL is required for Redis rate limiting")
        window = int(now // window_seconds)
        redis_key = f"rate_limit:{key}:{window_seconds}:{window}"
        client = self._client()
        increment = max(cost, 1)
        used = int(client.incrby(redis_key, increment))
        if used == increment:
            client.expire(redis_key, window_seconds + 1)
        return CounterResult(
            used=used,
            limit=limit,
            reset_after_seconds=_reset_after_seconds(now, window_seconds),
            provider=self.provider,
        )

    def reset(self, prefix: str = "") -> None:
        """Reset is intentionally narrow; Redis key scanning is avoided."""
        if prefix:
            self._client().delete(prefix)

    def _client(self) -> object:
        try:
            import redis
        except ImportError as exc:
            raise MissingProviderDependencyError("redis is required for Redis rate limiting") from exc
        return redis.Redis.from_url(self.redis_url)


@dataclass(frozen=True, slots=True)
class RateLimitPolicy:
    """Endpoint-aware API and GPU-job rate limiter."""

    settings: RateLimitSettings
    store: RateLimitStore | None = None

    def __post_init__(self) -> None:
        if self.store is None:
            object.__setattr__(self, "store", build_rate_limit_store(self.settings))

    def check(self, request: RateLimitRequest, now: float | None = None) -> RateLimitResult:
        """Return whether the request is allowed across all applicable limits."""
        active_now = time.time() if now is None else now
        checks = self._checks(request)
        most_restrictive: RateLimitResult | None = None
        for check in checks:
            counter = self.store.increment(  # type: ignore[union-attr]
                check.key,
                check.window_seconds,
                check.limit,
                check.cost,
                active_now,
            )
            result = RateLimitResult(
                allowed=counter.allowed,
                status_code=200 if counter.allowed else 429,
                rule=check.rule_name,
                key=check.key,
                limit=counter.limit,
                remaining=counter.remaining,
                retry_after_seconds=counter.reset_after_seconds,
                provider=counter.provider,
                message="ok" if counter.allowed else f"rate limit exceeded for {check.rule_name}",
            )
            if not result.allowed:
                return result
            if most_restrictive is None or result.remaining < most_restrictive.remaining:
                most_restrictive = result
        return most_restrictive or RateLimitResult(True, 200, "none", "", 0, 0, 0, self.store.provider)  # type: ignore[union-attr]

    def _checks(self, request: RateLimitRequest) -> tuple[RateLimitCheck, ...]:
        endpoint = request.endpoint or endpoint_for_path(request.path)
        identity = request.identity
        cost = max(int(request.cost), 1)
        base_rule = self._base_identity_rule(identity)
        endpoint_rule = self._endpoint_rule(endpoint)
        principal = identity.principal_key
        ip_key = f"ip:{identity.ip_address or 'unknown'}"
        checks: list[RateLimitCheck] = []
        checks.extend(self._rule_checks(base_rule, f"identity:{ip_key}", 1))
        if principal != ip_key:
            checks.extend(self._rule_checks(base_rule, f"identity:{principal}", 1))
        checks.extend(self._rule_checks(endpoint_rule, f"endpoint:{endpoint}:ip:{identity.ip_address or 'unknown'}", cost))
        checks.extend(self._rule_checks(endpoint_rule, f"endpoint:{endpoint}:principal:{principal}", cost))
        return tuple(checks)

    def _base_identity_rule(self, identity: RateLimitIdentity) -> RateLimitRule:
        if identity.is_authenticated:
            return RateLimitRule("authenticated", requests_per_minute=self.settings.authenticated_requests_per_minute)
        return RateLimitRule("anonymous", requests_per_minute=self.settings.anonymous_requests_per_minute)

    def _endpoint_rule(self, endpoint: str) -> RateLimitRule:
        if endpoint == "gpu_submit":
            return RateLimitRule(
                "gpu_submit",
                requests_per_hour=self.settings.gpu_submit_requests_per_hour,
                requests_per_day=self.settings.gpu_submit_requests_per_day,
                cost_sensitive=True,
            )
        if endpoint == "ingestion":
            return RateLimitRule("ingestion", requests_per_hour=self.settings.ingestion_requests_per_hour)
        if endpoint == "training":
            return RateLimitRule("training", requests_per_hour=self.settings.training_requests_per_hour)
        if endpoint == "features":
            return RateLimitRule("features", requests_per_hour=self.settings.features_requests_per_hour)
        if endpoint == "predict":
            return RateLimitRule("predict", requests_per_minute=self.settings.predict_requests_per_minute)
        if endpoint == "health":
            return RateLimitRule("health", requests_per_minute=self.settings.health_requests_per_minute)
        return RateLimitRule("api", requests_per_minute=self.settings.requests_per_minute + self.settings.burst)

    def _rule_checks(self, rule: RateLimitRule, key_prefix: str, request_cost: int) -> tuple[RateLimitCheck, ...]:
        cost = request_cost if rule.cost_sensitive else 1
        checks: list[RateLimitCheck] = []
        if rule.requests_per_minute is not None:
            checks.append(RateLimitCheck(rule.name, f"{key_prefix}:{rule.name}:minute", rule.requests_per_minute, MINUTE, cost))
        if rule.requests_per_hour is not None:
            checks.append(RateLimitCheck(rule.name, f"{key_prefix}:{rule.name}:hour", rule.requests_per_hour, HOUR, cost))
        if rule.requests_per_day is not None:
            checks.append(RateLimitCheck(rule.name, f"{key_prefix}:{rule.name}:day", rule.requests_per_day, DAY, cost))
        return tuple(checks)


def build_rate_limit_store(settings: RateLimitSettings) -> RateLimitStore:
    """Build the configured rate-limit store."""
    if settings.provider == "redis":
        return RedisRateLimitStore(settings.redis_url)
    return MemoryRateLimitStore()


def endpoint_for_path(path: str) -> str:
    """Map an API path to a named rate-limit endpoint class."""
    normalized = path.rstrip("/") or "/"
    if normalized.endswith("/ingest/run") or normalized == "/ingest/run":
        return "ingestion"
    if normalized.endswith("/features/build") or normalized == "/features/build":
        return "features"
    if normalized.endswith("/train/run") or normalized.endswith("/model/train") or normalized == "/train/run":
        return "training"
    if normalized.endswith("/compute/runpod/submit") or normalized == "/compute/runpod/submit":
        return "gpu_submit"
    if normalized.endswith("/compute/runpod/cancel") or normalized == "/compute/runpod/cancel":
        return "gpu_submit"
    if normalized.endswith("/predict") or normalized.endswith("/model/predict") or normalized == "/predict":
        return "predict"
    if normalized.endswith("/health") or normalized == "/health":
        return "health"
    return "api"


def rate_limit_settings_from_config(config: Mapping[str, object]) -> RateLimitSettings:
    """Build rate-limit settings from a `rate_limits:` config block."""
    payload = config.get("rate_limits", config)
    if not isinstance(payload, Mapping):
        payload = {}
    anonymous = _mapping(payload.get("anonymous"))
    authenticated = _mapping(payload.get("authenticated"))
    gpu_submit = _mapping(payload.get("gpu_submit"))
    ingestion = _mapping(payload.get("ingestion"))
    training = _mapping(payload.get("training"))
    features = _mapping(payload.get("features"))
    predict = _mapping(payload.get("predict"))
    health = _mapping(payload.get("health"))
    return RateLimitSettings(
        provider=str(payload.get("provider") or "memory"),
        requests_per_minute=_int(payload.get("requests_per_minute"), 60),
        burst=_int(payload.get("burst"), 10),
        redis_url=str(payload.get("redis_url") or ""),
        anonymous_requests_per_minute=_int(anonymous.get("requests_per_minute"), 20),
        authenticated_requests_per_minute=_int(authenticated.get("requests_per_minute"), 120),
        gpu_submit_requests_per_hour=_int(gpu_submit.get("requests_per_hour"), 3),
        gpu_submit_requests_per_day=_int(gpu_submit.get("requests_per_day"), 10),
        ingestion_requests_per_hour=_int(ingestion.get("requests_per_hour"), 10),
        training_requests_per_hour=_int(training.get("requests_per_hour"), 5),
        features_requests_per_hour=_int(features.get("requests_per_hour"), 20),
        predict_requests_per_minute=_int(predict.get("requests_per_minute"), 60),
        health_requests_per_minute=_int(health.get("requests_per_minute"), 600),
    )


def _reset_after_seconds(now: float, window_seconds: int) -> int:
    return max(window_seconds - int(now % window_seconds), 1)


def _mapping(value: object) -> Mapping[str, object]:
    return value if isinstance(value, Mapping) else {}


def _int(value: object, default: int) -> int:
    if value in (None, ""):
        return default
    return int(value)
