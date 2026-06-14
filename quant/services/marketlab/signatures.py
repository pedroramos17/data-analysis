"""MarketLab signature encoder fallbacks."""

from __future__ import annotations

from collections.abc import Sequence

from quant.services.marketlab.interfaces import BaseSignatureEncoder


class LeadLagSignatureEncoder(BaseSignatureEncoder):
    """Lead-lag signature normalization fallback."""

    def encode(self, values: Sequence[float]) -> list[float]:
        """Return normalized first differences."""
        if len(values) < 2:
            return [0.0 for _ in values]
        diffs = [
            float(values[index]) - float(values[index - 1])
            for index in range(1, len(values))
        ]
        scale = max(1.0, max(abs(value) for value in diffs))
        return [value / scale for value in diffs]
