"""Portfolio constraints for local Quant research optimizers."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field


@dataclass(frozen=True, slots=True)
class PortfolioConstraints:
    """Constraint envelope for long-only research portfolios.

    Example:
        `PortfolioConstraints(max_weight=0.10, liquidity_limits={"A": 0.02})`
    """

    budget: float = 1.0
    long_only: bool = True
    max_weight: float = 1.0
    group_limits: Mapping[str, Mapping[str, float]] = field(default_factory=dict)
    turnover_limit: float | None = None
    liquidity_limits: Mapping[str, float] = field(default_factory=dict)


def apply_portfolio_constraints(
    weights: Mapping[str, float],
    constraints: PortfolioConstraints,
) -> dict[str, float]:
    """Return weights normalized to budget and max weight.

    Example:
        `apply_portfolio_constraints({"A": 1.0}, PortfolioConstraints())`
    """
    cleaned = _long_only_weights(weights, constraints.long_only)
    normalized = _normalize_budget(cleaned, constraints.budget)
    capped = _cap_weights(normalized, constraints.max_weight, constraints.budget)
    validate_portfolio_constraints(capped, constraints)
    return capped


def validate_portfolio_constraints(
    weights: Mapping[str, float],
    constraints: PortfolioConstraints,
    asset_metadata: Mapping[str, Mapping[str, object]] | None = None,
    current_weights: Mapping[str, float] | None = None,
) -> None:
    """Raise when portfolio weights violate explicit constraints."""
    _validate_budget(weights, constraints.budget)
    _validate_long_only(weights, constraints.long_only)
    _validate_max_weight(weights, constraints.max_weight)
    _validate_group_limits(weights, constraints.group_limits, asset_metadata or {})
    _validate_turnover(weights, current_weights or {}, constraints.turnover_limit)
    _validate_liquidity(weights, constraints.liquidity_limits)


def portfolio_turnover(
    target_weights: Mapping[str, float],
    current_weights: Mapping[str, float],
) -> float:
    """Return one-way absolute turnover between current and target weights."""
    symbols = set(target_weights) | set(current_weights)
    return sum(
        _weight_delta(target_weights, current_weights, symbol) for symbol in symbols
    )


def _long_only_weights(
    weights: Mapping[str, float],
    long_only: bool,
) -> dict[str, float]:
    if not long_only:
        return {symbol: float(weight) for symbol, weight in weights.items()}
    return {symbol: max(0.0, float(weight)) for symbol, weight in weights.items()}


def _normalize_budget(weights: Mapping[str, float], budget: float) -> dict[str, float]:
    total = sum(weights.values())
    if total <= 0:
        raise ValueError(f"Invalid weights {dict(weights)!r}; expected positive sum")
    return {symbol: budget * value / total for symbol, value in weights.items()}


def _cap_weights(
    weights: Mapping[str, float],
    max_weight: float,
    budget: float,
) -> dict[str, float]:
    if max_weight * len(weights) + 1e-12 < budget:
        raise ValueError(f"Invalid max_weight {max_weight!r}; expected feasible budget")
    capped = {symbol: min(weight, max_weight) for symbol, weight in weights.items()}
    return _redistribute_residual(capped, weights, max_weight, budget)


def _redistribute_residual(
    capped: Mapping[str, float],
    original: Mapping[str, float],
    max_weight: float,
    budget: float,
) -> dict[str, float]:
    result = dict(capped)
    for _step in range(max(1, len(result))):
        residual = budget - sum(result.values())
        if residual <= 1e-12:
            return result
        room_symbols = [
            symbol for symbol, weight in result.items() if weight < max_weight
        ]
        _add_residual(result, original, room_symbols, residual, max_weight)
    return result


def _add_residual(
    result: dict[str, float],
    original: Mapping[str, float],
    symbols: list[str],
    residual: float,
    max_weight: float,
) -> None:
    base = sum(max(original.get(symbol, 0.0), 0.0) for symbol in symbols)
    base = base or len(symbols)
    for symbol in symbols:
        share = max(original.get(symbol, 0.0), 0.0) / base if base else 0.0
        result[symbol] = min(max_weight, result[symbol] + residual * share)


def _validate_budget(weights: Mapping[str, float], budget: float) -> None:
    if abs(sum(weights.values()) - budget) <= 1e-6:
        return
    raise ValueError(
        f"Invalid weight sum {sum(weights.values())!r}; expected {budget!r}"
    )


def _validate_long_only(weights: Mapping[str, float], long_only: bool) -> None:
    if not long_only:
        return
    for symbol, weight in weights.items():
        if weight < -1e-12:
            raise ValueError(f"Invalid weight {weight!r} for {symbol}; expected >= 0")


def _validate_max_weight(weights: Mapping[str, float], max_weight: float) -> None:
    for symbol, weight in weights.items():
        if weight > max_weight + 1e-12:
            raise ValueError(
                f"Invalid weight {weight!r} for {symbol}; "
                f"expected <= {max_weight!r}"
            )


def _validate_group_limits(
    weights: Mapping[str, float],
    group_limits: Mapping[str, Mapping[str, float]],
    asset_metadata: Mapping[str, Mapping[str, object]],
) -> None:
    for group_field, limits in group_limits.items():
        exposures = _group_exposures(weights, group_field, asset_metadata)
        _validate_group_values(group_field, exposures, limits)


def _group_exposures(
    weights: Mapping[str, float],
    field: str,
    asset_metadata: Mapping[str, Mapping[str, object]],
) -> dict[str, float]:
    exposures: dict[str, float] = {}
    for symbol, weight in weights.items():
        value = str(asset_metadata.get(symbol, {}).get(field, "")).strip()
        if value:
            exposures[value] = exposures.get(value, 0.0) + weight
    return exposures


def _validate_group_values(
    field: str,
    exposures: Mapping[str, float],
    limits: Mapping[str, float],
) -> None:
    for value, exposure in exposures.items():
        limit = float(limits.get(value, 1.0))
        if exposure > limit + 1e-12:
            raise ValueError(
                f"Invalid {field} exposure {value}={exposure!r}; "
                f"expected <= {limit!r}"
            )


def _validate_turnover(
    weights: Mapping[str, float],
    current_weights: Mapping[str, float],
    turnover_limit: float | None,
) -> None:
    if turnover_limit is None:
        return
    turnover = portfolio_turnover(weights, current_weights)
    if turnover > turnover_limit + 1e-12:
        raise ValueError(
            f"Invalid turnover {turnover!r}; expected <= {turnover_limit!r}"
        )


def _validate_liquidity(
    weights: Mapping[str, float],
    liquidity_limits: Mapping[str, float],
) -> None:
    for symbol, limit in liquidity_limits.items():
        weight = float(weights.get(symbol, 0.0))
        if weight > float(limit) + 1e-12:
            raise ValueError(
                f"Invalid liquidity weight {symbol}={weight!r}; "
                f"expected <= {limit!r}"
            )


def _weight_delta(
    target_weights: Mapping[str, float],
    current_weights: Mapping[str, float],
    symbol: str,
) -> float:
    return abs(target_weights.get(symbol, 0.0) - current_weights.get(symbol, 0.0))
