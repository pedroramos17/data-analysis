"""MarketLab decomposition fallbacks."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from quant4.services.marketlab.interfaces import BaseDecomposer


@dataclass(frozen=True, slots=True)
class DecompositionResult:
    """Decomposition result with reconstruction diagnostics."""

    components: list[list[float]]
    reconstruction_error: float
    method: str


class IMFDecomposer(BaseDecomposer):
    """Identity IMF fallback when decomposition dependencies are missing."""

    def decompose(self, values: Sequence[float]) -> DecompositionResult:
        """Return identity components and zero reconstruction error."""
        component = [float(value) for value in values]
        error = _reconstruction_error(component, values)
        return DecompositionResult([component], error, "identity_fallback")


def _reconstruction_error(component: Sequence[float], values: Sequence[float]) -> float:
    if not values:
        return 0.0
    pairs = zip(component, values, strict=False)
    errors = [abs(float(left) - float(right)) for left, right in pairs]
    return max(errors) if errors else 0.0
