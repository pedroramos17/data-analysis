"""Risk run report assembly and persistence."""

from __future__ import annotations

from collections.abc import Mapping, Sequence

from quant4.services.regimes.detectors import regime_summary
from quant4.services.registry import stable_config_hash
from quant4.services.risk.covariance import ewma_volatility, historical_volatility
from quant4.services.risk.liquidity_risk import estimate_liquidity_risk
from quant4.services.risk.risk_attribution import (
    build_model_risk_fields,
    build_risk_sections,
)
from quant4.services.risk.tail_risk import (
    drawdown_duration,
    expected_shortfall,
    historical_var,
    max_drawdown,
)
from sourceflow.config.feature_flags import require_feature


def run_risk_analysis(
    name: str,
    returns: Sequence[float],
    prices: Sequence[float],
    volumes: Sequence[float],
    random_seed: int = 0,
    provenance: Mapping[str, object] | None = None,
) -> object:
    """Persist a separated Quant4 risk report in RiskRun.metrics_json.

    Example:
        `run_risk_analysis("risk", [0.01], [100.0], [1000.0])`
    """
    require_feature("QUANT4_RISK_CORE")
    from quant4.models import RiskRun

    config = {"model": "mvp2_risk_core", "count": len(returns)}
    return RiskRun.objects.create(
        name=name,
        component_name="mvp2_risk_core",
        config_json=config,
        config_hash=stable_config_hash(config),
        random_seed=random_seed,
        feature_schema_json=_risk_feature_schema(),
        metrics_json=_risk_metrics(returns, prices, volumes),
        provenance_json=dict(provenance or {}),
        status="RESEARCH_ONLY",
    )


def _risk_metrics(
    returns: Sequence[float],
    prices: Sequence[float],
    volumes: Sequence[float],
) -> dict[str, object]:
    return build_risk_sections(
        forecast_risk=_forecast_risk(returns),
        portfolio_risk=_portfolio_risk(returns, prices),
        liquidity_risk=estimate_liquidity_risk(returns, volumes),
        model_risk=build_model_risk_fields("mvp2_risk_core"),
        regime_risk=regime_summary(returns, prices),
    )


def _risk_feature_schema() -> dict[str, object]:
    return {
        "returns": "past_sequence_float",
        "prices": "past_sequence_float",
        "volumes": "past_sequence_float",
    }


def _forecast_risk(returns: Sequence[float]) -> dict[str, object]:
    return {
        "historical_volatility": historical_volatility(returns),
        "ewma_volatility": ewma_volatility(returns),
    }


def _portfolio_risk(
    returns: Sequence[float],
    prices: Sequence[float],
) -> dict[str, object]:
    return {
        "historical_var": historical_var(returns),
        "expected_shortfall": expected_shortfall(returns),
        "max_drawdown": max_drawdown(prices),
        "drawdown_duration": drawdown_duration(prices),
    }
