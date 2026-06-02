"""Lightweight TDA fallback validators."""

from __future__ import annotations

from collections.abc import Sequence

from quant4.services.marketlab.interfaces import BaseTDAValidator


class LightweightTDAValidator(BaseTDAValidator):
    """Validate topology using a dependency-free distance summary."""

    def topology_loss(
        self,
        original: Sequence[float],
        candidate: Sequence[float],
    ) -> float:
        """Return absolute difference in simple path variation."""
        return abs(_variation(original) - _variation(candidate))


def _variation(values: Sequence[float]) -> float:
    if len(values) < 2:
        return 0.0
    return sum(
        abs(float(values[index]) - float(values[index - 1]))
        for index in range(1, len(values))
    )
