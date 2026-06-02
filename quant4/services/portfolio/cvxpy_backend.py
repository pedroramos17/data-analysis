"""Optional CVXPY portfolio backend boundary."""

from __future__ import annotations

from quant4.services.portfolio.optional_backends import require_portfolio_backend


class CVaROptimizer:
    """Optional CVaR optimizer backed by CVXPY when installed."""

    def __init__(self, required_module: str = "cvxpy") -> None:
        self.required_module = required_module

    def optimize(self) -> object:
        """Fail clearly when CVXPY is unavailable."""
        require_portfolio_backend("cvxpy_cvar", self.required_module)
        return {"backend": "cvxpy", "objective": "cvar"}
