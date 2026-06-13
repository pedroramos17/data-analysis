"""MarketLab graph sampling fallbacks."""

from __future__ import annotations

from collections.abc import Sequence

from quant.services.marketlab.interfaces import BaseGraphSampler


class PrefixGraphSampler(BaseGraphSampler):
    """Sample a deterministic prefix of graph nodes."""

    def __init__(self, limit: int = 10) -> None:
        self.limit = limit

    def sample(self, nodes: Sequence[object]) -> list[object]:
        """Return at most `limit` nodes."""
        return list(nodes[: self.limit])
