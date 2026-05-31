"""Portfolio constraints for multifractal research allocation."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field


@dataclass(frozen=True, slots=True)
class MultifractalPortfolioConstraints:
    """Constraint envelope for local multifractal portfolio tests.

    Example:
        `constraints = MultifractalPortfolioConstraints(max_weight=0.25)`
    """

    budget: float = 1.0
    long_only: bool = True
    max_weight: float = 1.0
    asset_class_limits: Mapping[str, float] = field(default_factory=dict)
    cluster_limit: float = 1.0


def apply_multifractal_constraints(
    weights: Mapping[str, float],
    constraints: MultifractalPortfolioConstraints,
    asset_metadata: Mapping[str, Mapping[str, str]] | None = None,
    graph_clusters: Mapping[str, str] | None = None,
) -> dict[str, float]:
    """Apply budget, long-only, max-weight, and exposure constraints.

    Example:
        `weights = apply_multifractal_constraints({"A": 1.0}, constraints)`
    """
    cleaned = _clean_weights(weights, constraints.long_only)
    normalized = _normalize(cleaned, constraints.budget)
    capped = _cap_weights(normalized, constraints.max_weight, constraints.budget)
    _validate_asset_class(capped, constraints, asset_metadata or {})
    _validate_clusters(capped, constraints.cluster_limit, graph_clusters or {})
    return capped


def constraints_report(
    weights: Mapping[str, float],
    constraints: MultifractalPortfolioConstraints,
    graph_clusters: Mapping[str, str] | None = None,
) -> dict[str, object]:
    """Return explicit constraint diagnostics for reports."""
    return {
        "budget_ok": abs(sum(weights.values()) - constraints.budget) <= 1e-6,
        "max_weight_ok": max(weights.values(), default=0.0) <= constraints.max_weight,
        "cluster_exposure": cluster_exposures(weights, graph_clusters or {}),
    }


def cluster_exposures(
    weights: Mapping[str, float],
    graph_clusters: Mapping[str, str],
) -> dict[str, float]:
    """Aggregate weights by graph-derived cluster label."""
    exposures: dict[str, float] = {}
    for symbol, weight in weights.items():
        cluster = graph_clusters.get(symbol, f"single:{symbol}")
        exposures[cluster] = exposures.get(cluster, 0.0) + weight
    return exposures


def _clean_weights(
    weights: Mapping[str, float],
    long_only: bool,
) -> dict[str, float]:
    if not long_only:
        return {symbol: float(weight) for symbol, weight in weights.items()}
    return {symbol: max(0.0, float(weight)) for symbol, weight in weights.items()}


def _normalize(weights: Mapping[str, float], budget: float) -> dict[str, float]:
    total = sum(weights.values())
    if total <= 0.0:
        raise ValueError(f"Invalid weights {dict(weights)!r}; expected positive sum")
    return {symbol: budget * weight / total for symbol, weight in weights.items()}


def _cap_weights(
    weights: Mapping[str, float],
    max_weight: float,
    budget: float,
) -> dict[str, float]:
    if max_weight * len(weights) + 1e-12 < budget:
        raise ValueError(f"Invalid max_weight {max_weight!r}; expected feasible cap")
    result = {symbol: min(weight, max_weight) for symbol, weight in weights.items()}
    return _redistribute(result, max_weight, budget)


def _redistribute(
    weights: Mapping[str, float],
    max_weight: float,
    budget: float,
) -> dict[str, float]:
    result = dict(weights)
    for _step in range(max(1, len(result))):
        residual = budget - sum(result.values())
        if residual <= 1e-12:
            return result
        room = [symbol for symbol, weight in result.items() if weight < max_weight]
        _add_equal_room(result, room, residual, max_weight)
    return result


def _add_equal_room(
    result: dict[str, float],
    symbols: list[str],
    residual: float,
    max_weight: float,
) -> None:
    if not symbols:
        return
    share = residual / len(symbols)
    for symbol in symbols:
        result[symbol] = min(max_weight, result[symbol] + share)


def _validate_asset_class(
    weights: Mapping[str, float],
    constraints: MultifractalPortfolioConstraints,
    asset_metadata: Mapping[str, Mapping[str, str]],
) -> None:
    exposures = _asset_class_exposures(weights, asset_metadata)
    for asset_class, exposure in exposures.items():
        limit = constraints.asset_class_limits.get(asset_class, 1.0)
        if exposure <= limit + 1e-12:
            continue
        raise ValueError(
            f"Invalid asset_class exposure {asset_class}={exposure!r}; "
            f"expected <= {limit!r}"
        )


def _asset_class_exposures(
    weights: Mapping[str, float],
    asset_metadata: Mapping[str, Mapping[str, str]],
) -> dict[str, float]:
    exposures: dict[str, float] = {}
    for symbol, weight in weights.items():
        asset_class = asset_metadata.get(symbol, {}).get("asset_class", "")
        if asset_class:
            exposures[asset_class] = exposures.get(asset_class, 0.0) + weight
    return exposures


def _validate_clusters(
    weights: Mapping[str, float],
    cluster_limit: float,
    graph_clusters: Mapping[str, str],
) -> None:
    for cluster, exposure in cluster_exposures(weights, graph_clusters).items():
        if exposure <= cluster_limit + 1e-12:
            continue
        raise ValueError(
            f"Invalid cluster exposure {cluster}={exposure!r}; "
            f"expected <= {cluster_limit!r}"
        )
