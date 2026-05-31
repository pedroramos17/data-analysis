"""CPU-friendly multifractal portfolio optimizers."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from quant4.services.multifractal.portfolio.constraints import (
    MultifractalPortfolioConstraints,
    apply_multifractal_constraints,
    constraints_report,
)
from quant4.services.multifractal.portfolio.objectives import (
    inverse_variance_scores,
    multifractal_penalty,
    multifractal_risk_contribution,
    risk_contribution,
)


@dataclass(frozen=True, slots=True)
class MultifractalPortfolioResult:
    """Serializable multifractal allocation output.

    Example:
        `payload = result.to_json_dict()`
    """

    weights: dict[str, float]
    risk_contribution: dict[str, float]
    multifractal_risk_contribution: dict[str, float]
    turnover_estimate: float
    constraints_report: dict[str, object]
    warnings: tuple[str, ...]

    def to_json_dict(self) -> dict[str, object]:
        """Return a JSON-serializable result."""
        return {
            "weights": self.weights,
            "risk_contribution": self.risk_contribution,
            "multifractal_risk_contribution": self.multifractal_risk_contribution,
            "turnover_estimate": self.turnover_estimate,
            "constraints_report": self.constraints_report,
            "warnings": list(self.warnings),
            "claims_factor_validity": False,
        }


def minimum_variance_weights(
    symbols: Sequence[str],
    covariance: Sequence[Sequence[float]],
    budget: float = 1.0,
) -> dict[str, float]:
    """Return inverse-variance minimum-variance proxy weights.

    Example:
        `weights = minimum_variance_weights(["A"], [[0.01]])`
    """
    _validate_symbols(symbols)
    return _normalize(inverse_variance_scores(symbols, covariance), budget)


def risk_parity_weights(
    symbols: Sequence[str],
    covariance: Sequence[Sequence[float]],
    budget: float = 1.0,
) -> dict[str, float]:
    """Return a diagonal risk-parity baseline."""
    return minimum_variance_weights(symbols, covariance, budget)


def optimize_multifractal_adjusted_portfolio(
    symbols: Sequence[str],
    covariance: Sequence[Sequence[float]],
    risk_features: Mapping[str, Mapping[str, float]],
    regime_labels: Mapping[str, str] | None = None,
    constraints: MultifractalPortfolioConstraints | None = None,
    current_weights: Mapping[str, float] | None = None,
    graph_clusters: Mapping[str, str] | None = None,
) -> MultifractalPortfolioResult:
    """Allocate with variance, multifractal, regime, and graph penalties.

    Example:
        `result = optimize_multifractal_adjusted_portfolio(symbols, covariance, {})`
    """
    active_constraints = constraints or MultifractalPortfolioConstraints()
    base = inverse_variance_scores(symbols, covariance)
    penalized = _penalized_scores(base, risk_features, regime_labels or {})
    weights = _constrained_weights(penalized, active_constraints, graph_clusters or {})
    return _result(weights, covariance, risk_features, current_weights, graph_clusters)


def _penalized_scores(
    scores: Mapping[str, float],
    risk_features: Mapping[str, Mapping[str, float]],
    regime_labels: Mapping[str, str],
) -> dict[str, float]:
    return {
        symbol: score
        * multifractal_penalty(
            risk_features.get(symbol, {}),
            regime_labels.get(symbol, ""),
        )
        for symbol, score in scores.items()
    }


def _constrained_weights(
    scores: Mapping[str, float],
    constraints: MultifractalPortfolioConstraints,
    graph_clusters: Mapping[str, str],
) -> dict[str, float]:
    raw = _normalize(scores, constraints.budget)
    try:
        return apply_multifractal_constraints(raw, constraints, {}, graph_clusters)
    except ValueError:
        fallback = _equal_scores(scores)
        return apply_multifractal_constraints(fallback, constraints, {}, {})


def _result(
    weights: dict[str, float],
    covariance: Sequence[Sequence[float]],
    risk_features: Mapping[str, Mapping[str, float]],
    current_weights: Mapping[str, float] | None,
    graph_clusters: Mapping[str, str] | None,
) -> MultifractalPortfolioResult:
    constraints = MultifractalPortfolioConstraints()
    return MultifractalPortfolioResult(
        weights=weights,
        risk_contribution=risk_contribution(weights, covariance),
        multifractal_risk_contribution=multifractal_risk_contribution(
            weights, risk_features
        ),
        turnover_estimate=_turnover(weights, current_weights or {}),
        constraints_report=constraints_report(weights, constraints, graph_clusters),
        warnings=("research_allocation_not_execution",),
    )


def _normalize(scores: Mapping[str, float], budget: float) -> dict[str, float]:
    positive = {symbol: max(0.0, float(score)) for symbol, score in scores.items()}
    total = sum(positive.values())
    if total <= 0.0:
        return _equal_scores(scores, budget)
    return {symbol: budget * score / total for symbol, score in positive.items()}


def _equal_scores(
    scores: Mapping[str, float],
    budget: float = 1.0,
) -> dict[str, float]:
    if not scores:
        raise ValueError(f"Invalid scores {dict(scores)!r}; expected non-empty mapping")
    weight = budget / len(scores)
    return {symbol: weight for symbol in scores}


def _turnover(
    weights: Mapping[str, float],
    current_weights: Mapping[str, float],
) -> float:
    symbols = set(weights) | set(current_weights)
    return sum(
        abs(weights.get(symbol, 0.0) - current_weights.get(symbol, 0.0))
        for symbol in symbols
    )


def _validate_symbols(symbols: Sequence[str]) -> None:
    if symbols:
        return
    raise ValueError(f"Invalid symbols {symbols!r}; expected non-empty sequence")
