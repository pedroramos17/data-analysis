"""MarketLab change-point fallback detectors."""

from __future__ import annotations

from collections.abc import Sequence

from quant.services.marketlab.interfaces import BaseRegimeDetector


class MeanShiftRegimeDetector(BaseRegimeDetector):
    """Detect a simple mean-shift proxy without optional dependencies."""

    def detect(self, values: Sequence[float]) -> dict[str, object]:
        """Return mean-shift metadata."""
        if not values:
            return {"label": "empty", "change_points": []}
        midpoint = len(values) // 2
        return {"label": "mean_shift_proxy", "change_points": [midpoint]}
