"""Optional Riskfolio portfolio backend boundary."""

from __future__ import annotations

from quant.services.portfolio.optional_backends import require_portfolio_backend


class RiskfolioOptimizer:
    """Optional Riskfolio optimizer wrapper."""

    def __init__(self, required_module: str = "riskfolio") -> None:
        self.required_module = required_module

    def optimize(self) -> object:
        """Fail clearly when Riskfolio is unavailable."""
        require_portfolio_backend("riskfolio", self.required_module)
        return {"backend": "riskfolio"}
