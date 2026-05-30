"""Fundamental-analysis feature helpers."""

from __future__ import annotations

from collections.abc import Mapping


def fundamental_similarity(
    left: Mapping[str, float],
    right: Mapping[str, float],
) -> float:
    """Return similarity from shared fundamental metric values.

    Example:
        `fundamental_similarity({"gross_margin": .4}, {"gross_margin": .5})`
    """
    keys = sorted(set(left) & set(right))
    if not keys:
        return 0.0
    distance = sum(abs(float(left[key]) - float(right[key])) for key in keys)
    return max(0.0, 1.0 - distance / len(keys))


def valuation_profitability_leverage_features(
    facts: Mapping[str, float],
) -> dict[str, float]:
    """Build basic profitability, leverage, and growth factors.

    Example:
        `features = valuation_profitability_leverage_features(facts)`
    """
    revenue = _value(facts, "revenue")
    gross_profit = _value(facts, "gross_profit")
    debt = _value(facts, "debt")
    equity = _value(facts, "equity")
    return {
        "gross_margin": _ratio(gross_profit, revenue),
        "debt_to_equity": _ratio(debt, equity),
        "current_ratio": _ratio(
            _value(facts, "current_assets"), _value(facts, "current_liabilities")
        ),
        "net_margin": _ratio(_value(facts, "net_income"), revenue),
    }


def filing_lag_days(filed_at_ordinal: int, period_end_ordinal: int) -> int:
    """Return days between fiscal period end and filing availability.

    Example:
        `filing_lag_days(10, 1) == 9`
    """
    return max(0, filed_at_ordinal - period_end_ordinal)


def _value(facts: Mapping[str, float], key: str) -> float:
    return float(facts.get(key, 0.0))


def _ratio(numerator: float, denominator: float) -> float:
    return numerator / denominator if denominator else 0.0
