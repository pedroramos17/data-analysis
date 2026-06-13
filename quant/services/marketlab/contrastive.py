"""MarketLab contrastive learning fallback."""

from __future__ import annotations

from collections.abc import Sequence

from quant.services.marketlab.interfaces import BaseContrastiveLearner


class IdentityContrastiveLearner(BaseContrastiveLearner):
    """Return local metadata instead of training a heavy model."""

    def fit(self, rows: Sequence[object]) -> dict[str, object]:
        """Return fit metadata for local smoke tests."""
        return {"method": "identity_fallback", "row_count": len(rows)}
