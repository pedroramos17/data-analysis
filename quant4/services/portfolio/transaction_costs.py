"""Transaction cost models for Quant4 portfolio research."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from quant4.services.portfolio.constraints import portfolio_turnover


@dataclass(frozen=True, slots=True)
class TransactionCostModel:
    """Simple local transaction cost parameters.

    Example:
        `TransactionCostModel(bps_per_turnover=10.0)`
    """

    bps_per_turnover: float = 0.0
    fixed_cost_per_trade: float = 0.0
    market_impact_bps: float = 0.0


def calculate_transaction_cost_drag(
    current_weights: Mapping[str, float],
    target_weights: Mapping[str, float],
    portfolio_value: float,
    model: TransactionCostModel,
) -> dict[str, float]:
    """Return turnover, notional traded, and estimated cost drag.

    Example:
        `calculate_transaction_cost_drag({"A": 0.5}, {"A": 1.0}, 1000, model)`
    """
    turnover = portfolio_turnover(target_weights, current_weights)
    trade_count = _trade_count(current_weights, target_weights)
    traded_notional = turnover * float(portfolio_value)
    variable_cost = traded_notional * _bps_to_rate(_total_bps(model))
    fixed_cost = trade_count * model.fixed_cost_per_trade
    total_cost = variable_cost + fixed_cost
    return {
        "turnover": turnover,
        "traded_notional": traded_notional,
        "estimated_cost": total_cost,
        "cost_drag": 0.0 if portfolio_value == 0 else total_cost / portfolio_value,
    }


def _trade_count(
    current_weights: Mapping[str, float],
    target_weights: Mapping[str, float],
) -> int:
    symbols = set(current_weights) | set(target_weights)
    return sum(
        int(
            abs(target_weights.get(symbol, 0.0) - current_weights.get(symbol, 0.0))
            > 1e-12
        )
        for symbol in symbols
    )


def _total_bps(model: TransactionCostModel) -> float:
    return model.bps_per_turnover + model.market_impact_bps


def _bps_to_rate(value: float) -> float:
    return value / 10000.0
