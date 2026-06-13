"""Local-first portfolio optimizers and PortfolioRun persistence."""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path

from quant.services.portfolio.constraints import (
    PortfolioConstraints,
    apply_portfolio_constraints,
    portfolio_turnover,
)
from quant.services.portfolio.transaction_costs import (
    TransactionCostModel,
    calculate_transaction_cost_drag,
)
from quant.services.registry import stable_config_hash
from quant.services.run_metadata import DateRange, build_run_metadata_fields
from sourceflow.config.feature_flags import require_feature


@dataclass(frozen=True, slots=True)
class PortfolioOptimizationResult:
    """Serializable portfolio optimizer output.

    Example:
        `PortfolioOptimizationResult({"AAA": 1.0}, {}, {}, {})`
    """

    weights: dict[str, float]
    trades: dict[str, float]
    metrics: dict[str, object]
    risk_report: dict[str, object]
    metadata: dict[str, object] = field(default_factory=dict)


class EqualWeightOptimizer:
    """Allocate equal budget to each symbol."""

    def optimize(
        self,
        symbols: Sequence[str],
        budget: float = 1.0,
    ) -> PortfolioOptimizationResult:
        """Return equal-weight allocations."""
        weights = _equal_weights(symbols, budget)
        return _result("equal_weight", weights)


class InverseVolatilityOptimizer:
    """Allocate by inverse volatility."""

    def optimize(
        self,
        symbols: Sequence[str],
        volatilities: Mapping[str, float],
        budget: float = 1.0,
    ) -> PortfolioOptimizationResult:
        """Return inverse-volatility weights."""
        scores = {
            symbol: _inverse_positive(volatilities.get(symbol, 0.0))
            for symbol in symbols
        }
        weights = _normalize_scores(scores, budget)
        return _result("inverse_volatility", weights)


class MinimumVarianceOptimizer:
    """Allocate by inverse covariance diagonal."""

    def optimize(
        self,
        symbols: Sequence[str],
        covariance: Sequence[Sequence[float]],
        budget: float = 1.0,
    ) -> PortfolioOptimizationResult:
        """Return a diagonal minimum-variance proxy."""
        variances = _diagonal_variances(symbols, covariance)
        scores = {symbol: _inverse_positive(variances[symbol]) for symbol in symbols}
        return _result("minimum_variance", _normalize_scores(scores, budget))


class MaxSharpePrototypeOptimizer:
    """Prototype Sharpe-like optimizer for local research baselines."""

    def optimize(
        self,
        symbols: Sequence[str],
        expected_returns: Mapping[str, float],
        covariance: Sequence[Sequence[float]],
        constraints: PortfolioConstraints | None = None,
    ) -> PortfolioOptimizationResult:
        """Return max-return-per-variance prototype weights."""
        budget = constraints.budget if constraints else 1.0
        variances = _diagonal_variances(symbols, covariance)
        scores = _sharpe_scores(symbols, expected_returns, variances)
        weights = _normalize_scores(scores, budget)
        if constraints is not None:
            weights = apply_portfolio_constraints(weights, constraints)
        return _result("max_sharpe_prototype", weights)


def optimize_portfolio(
    symbols: Sequence[str],
    optimizer_name: str,
    covariance: Sequence[Sequence[float]] | None = None,
    expected_returns: Mapping[str, float] | None = None,
    volatilities: Mapping[str, float] | None = None,
) -> PortfolioOptimizationResult:
    """Dispatch a named local portfolio optimizer.

    Example:
        `optimize_portfolio(["AAA"], "equal_weight")`
    """
    require_feature("QUANT_PORTFOLIO_CORE")
    if optimizer_name == "equal_weight":
        return EqualWeightOptimizer().optimize(symbols)
    if optimizer_name == "inverse_volatility":
        return InverseVolatilityOptimizer().optimize(symbols, volatilities or {})
    if optimizer_name == "minimum_variance":
        return MinimumVarianceOptimizer().optimize(symbols, covariance or [])
    if optimizer_name == "max_sharpe":
        return MaxSharpePrototypeOptimizer().optimize(
            symbols, expected_returns or {}, covariance or []
        )
    raise ValueError(
        f"Invalid optimizer {optimizer_name!r}; "
        "expected supported Quant portfolio optimizer"
    )


def persist_portfolio_run(
    name: str,
    result: PortfolioOptimizationResult,
    output_dir: str,
    data_range: DateRange,
    split_range: DateRange,
    current_weights: Mapping[str, float] | None = None,
    random_seed: int = 0,
) -> object:
    """Persist weights, trades, and metadata in shared PortfolioRun."""
    from quant.models import PortfolioRun

    enriched = _with_trades(result, current_weights or {})
    paths = _write_portfolio_artifacts(name, output_dir, enriched)
    metrics = _metrics(enriched, current_weights or {})
    config = {"engine": "quant_portfolio", "optimizer": result.metadata["optimizer"]}
    return PortfolioRun.objects.create(
        name=name,
        component_name="quant_portfolio",
        config_json=config,
        config_hash=stable_config_hash(config),
        weights_path=paths["weights_path"],
        trades_path=paths["trades_path"],
        metrics_json=metrics,
        risk_report_json=enriched.risk_report,
        feature_schema_json=_feature_schema(),
        status="RESEARCH_ONLY",
        **build_run_metadata_fields(
            data_range,
            split_range,
            random_seed,
            {"engine": "quant_portfolio"},
        ),
    )


def _result(
    optimizer: str,
    weights: Mapping[str, float],
) -> PortfolioOptimizationResult:
    normalized = {symbol: float(weight) for symbol, weight in weights.items()}
    return PortfolioOptimizationResult(
        weights=normalized,
        trades={},
        metrics={"optimizer": optimizer},
        risk_report=_risk_report(normalized),
        metadata={"optimizer": optimizer},
    )


def _with_trades(
    result: PortfolioOptimizationResult,
    current_weights: Mapping[str, float],
) -> PortfolioOptimizationResult:
    trades = _trade_deltas(current_weights, result.weights)
    return PortfolioOptimizationResult(
        weights=result.weights,
        trades=trades,
        metrics=result.metrics,
        risk_report=result.risk_report,
        metadata=result.metadata,
    )


def _equal_weights(symbols: Sequence[str], budget: float) -> dict[str, float]:
    if not symbols:
        raise ValueError(f"Invalid symbols {symbols!r}; expected non-empty sequence")
    weight = float(budget) / len(symbols)
    return {str(symbol): weight for symbol in symbols}


def _normalize_scores(scores: Mapping[str, float], budget: float) -> dict[str, float]:
    positive = {symbol: max(0.0, float(score)) for symbol, score in scores.items()}
    if sum(positive.values()) <= 0:
        return _equal_weights(list(scores), budget)
    total_score = sum(positive.values())
    return {symbol: budget * score / total_score for symbol, score in positive.items()}


def _inverse_positive(value: float) -> float:
    return 0.0 if value <= 0 else 1.0 / float(value)


def _diagonal_variances(
    symbols: Sequence[str],
    covariance: Sequence[Sequence[float]],
) -> dict[str, float]:
    return {
        str(symbol): _variance_at(covariance, index)
        for index, symbol in enumerate(symbols)
    }


def _variance_at(covariance: Sequence[Sequence[float]], index: int) -> float:
    if index >= len(covariance) or index >= len(covariance[index]):
        return 0.0
    return max(float(covariance[index][index]), 0.0)


def _sharpe_scores(
    symbols: Sequence[str],
    expected_returns: Mapping[str, float],
    variances: Mapping[str, float],
) -> dict[str, float]:
    return {
        str(symbol): max(0.0, float(expected_returns.get(symbol, 0.0)))
        * _inverse_positive(variances[str(symbol)])
        for symbol in symbols
    }


def _trade_deltas(
    current_weights: Mapping[str, float],
    target_weights: Mapping[str, float],
) -> dict[str, float]:
    symbols = sorted(set(current_weights) | set(target_weights))
    return {
        symbol: target_weights.get(symbol, 0.0) - current_weights.get(symbol, 0.0)
        for symbol in symbols
    }


def _write_portfolio_artifacts(
    name: str,
    output_dir: str,
    result: PortfolioOptimizationResult,
) -> dict[str, str]:
    root = Path(output_dir)
    root.mkdir(parents=True, exist_ok=True)
    paths = _portfolio_paths(root, name)
    _write_json(paths["weights_path"], {"weights": result.weights})
    _write_json(paths["trades_path"], {"trades": result.trades})
    return paths


def _portfolio_paths(root: Path, name: str) -> dict[str, str]:
    safe_name = "".join(
        char if char.isalnum() or char in "-_" else "_" for char in name
    )
    return {
        "weights_path": str(root / f"{safe_name}_weights.json"),
        "trades_path": str(root / f"{safe_name}_trades.json"),
    }


def _write_json(path: str, payload: Mapping[str, object]) -> None:
    Path(path).write_text(json.dumps(payload, sort_keys=True), encoding="utf-8")


def _metrics(
    result: PortfolioOptimizationResult,
    current_weights: Mapping[str, float],
) -> dict[str, object]:
    cost = calculate_transaction_cost_drag(
        current_weights,
        result.weights,
        1.0,
        TransactionCostModel(),
    )
    return result.metrics | {
        "turnover": portfolio_turnover(result.weights, current_weights),
        "cost_drag": cost,
    }


def _risk_report(weights: Mapping[str, float]) -> dict[str, object]:
    return {
        "claim_scope": "portfolio_research",
        "gross_exposure": sum(abs(weight) for weight in weights.values()),
        "causality_claim": False,
    }


def _feature_schema() -> dict[str, object]:
    return {
        "weights": "symbol_to_float",
        "trades": "simulated_rebalance_delta",
        "claim_scope": "research_only_no_execution",
    }
