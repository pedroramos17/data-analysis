"""Black-Litterman style local return blending."""

from __future__ import annotations

from collections.abc import Mapping


def blend_black_litterman_returns(
    prior_returns: Mapping[str, float],
    views: Mapping[str, float],
    view_weight: float = 0.5,
) -> dict[str, float]:
    """Blend prior returns with local research views.

    Example:
        `blend_black_litterman_returns({"AAA": 0.02}, {"AAA": 0.03})`
    """
    bounded_weight = min(1.0, max(0.0, float(view_weight)))
    symbols = set(prior_returns) | set(views)
    return {
        symbol: _blend_value(prior_returns, views, symbol, bounded_weight)
        for symbol in symbols
    }


def _blend_value(
    prior_returns: Mapping[str, float],
    views: Mapping[str, float],
    symbol: str,
    view_weight: float,
) -> float:
    prior = float(prior_returns.get(symbol, 0.0))
    view = float(views.get(symbol, prior))
    return (1.0 - view_weight) * prior + view_weight * view
