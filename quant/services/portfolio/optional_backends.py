"""Shared optional backend checks for portfolio integrations."""

from __future__ import annotations

import importlib

from quant.services.registry import OptionalDependencyMissingError


def require_portfolio_backend(backend_name: str, module_name: str) -> None:
    """Raise a clear error when an optional portfolio backend is missing.

    Example:
        `require_portfolio_backend("cvxpy", "cvxpy")`
    """
    try:
        importlib.import_module(module_name)
    except ImportError as exc:
        raise OptionalDependencyMissingError(
            f"Component {backend_name!r} requires optional dependency "
            f"{module_name!r}; expected installed module"
        ) from exc
