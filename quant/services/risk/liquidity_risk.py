"""Liquidity risk models with non-LOB fallback."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from statistics import mean


def estimate_liquidity_risk(
    returns: Sequence[float],
    volumes: Sequence[float],
    lob_rows: Sequence[Mapping[str, object]] = (),
) -> dict[str, object]:
    """Estimate liquidity risk from LOB data or Amihud fallback.

    Example:
        `estimate_liquidity_risk([0.01], [1000.0])`
    """
    if lob_rows:
        return _lob_liquidity_metrics(lob_rows)
    return {
        "method": "amihud_fallback",
        "amihud_illiquidity": amihud_illiquidity(returns, volumes),
        "bid_ask_spread_available": False,
    }


def amihud_illiquidity(returns: Sequence[float], volumes: Sequence[float]) -> float:
    """Return Amihud-style absolute return per unit volume.

    Example:
        `amihud_illiquidity([0.01], [1000.0])`
    """
    pairs = zip(returns, volumes, strict=False)
    ratios = [_safe_ratio(abs(float(ret)), float(vol)) for ret, vol in pairs]
    return mean(ratios) if ratios else 0.0


def bid_ask_spread(lob_rows: Sequence[Mapping[str, object]]) -> float:
    """Return average bid-ask spread from LOB rows when available.

    Example:
        `bid_ask_spread([{"bid": 99, "ask": 101}])`
    """
    spreads = [float(row["ask"]) - float(row["bid"]) for row in lob_rows]
    return mean(spreads) if spreads else 0.0


def _lob_liquidity_metrics(
    lob_rows: Sequence[Mapping[str, object]],
) -> dict[str, object]:
    return {
        "method": "lob_bid_ask",
        "bid_ask_spread": bid_ask_spread(lob_rows),
        "bid_ask_spread_available": True,
    }


def _safe_ratio(numerator: float, denominator: float) -> float:
    if denominator == 0:
        return 0.0
    return numerator / denominator
