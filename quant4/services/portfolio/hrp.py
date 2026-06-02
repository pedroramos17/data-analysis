"""Optional HRP portfolio backend boundary."""

from __future__ import annotations

from collections.abc import Sequence

from quant4.services.portfolio.optional_backends import require_portfolio_backend


class HRPOptimizer:
    """Optional hierarchical risk parity backend wrapper."""

    def __init__(self, required_module: str = "quant4_optional_hrp") -> None:
        self.required_module = required_module

    def optimize(self, covariance: Sequence[Sequence[float]] | None = None) -> object:
        """Fail clearly until an HRP backend is installed."""
        require_portfolio_backend("hrp", self.required_module)
        return {"backend": "hrp", "covariance": covariance or []}
