"""Rate-limit provider interface."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True, slots=True)
class RateLimitDecision:
    """Provider-neutral rate-limit decision."""

    allowed: bool
    limit: int
    remaining: int
    reset_after_seconds: int
    provider: str


class RateLimitProvider(Protocol):
    """Rate-limit boundary for ingestion and API workloads.

    Example:
        `registry.get_rate_limit().allow("ingest:yfinance")`
    """

    def allow(self, key: str, cost: int = 1) -> RateLimitDecision:
        """Return whether a key may perform work now."""

    def reset(self, key: str) -> None:
        """Reset tracked counters for a key when supported."""

    def healthcheck(self) -> bool:
        """Return whether the rate-limit provider is usable."""
