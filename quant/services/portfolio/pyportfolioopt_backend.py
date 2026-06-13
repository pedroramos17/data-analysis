"""Optional PyPortfolioOpt backend boundary."""

from __future__ import annotations

from quant.services.portfolio.optional_backends import require_portfolio_backend


class PyPortfolioOptOptimizer:
    """Optional PyPortfolioOpt optimizer wrapper."""

    def __init__(self, required_module: str = "pypfopt") -> None:
        self.required_module = required_module

    def optimize(self) -> object:
        """Fail clearly when PyPortfolioOpt is unavailable."""
        require_portfolio_backend("pyportfolioopt", self.required_module)
        return {"backend": "pyportfolioopt"}
