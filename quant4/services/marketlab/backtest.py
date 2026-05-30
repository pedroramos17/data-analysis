"""MarketLab backtest metadata helpers."""

from __future__ import annotations

from quant4.services.registry import stable_config_hash


def create_backtest_run(name: str, metrics: dict[str, object]) -> object:
    """Persist a research-only backtest run through shared Quant4 models."""
    from quant4.models import BacktestRun

    config = {"engine": "marketlab", "mode": "research_backtest"}
    return BacktestRun.objects.create(
        name=name,
        component_name="marketlab_backtest",
        config_json=config,
        config_hash=stable_config_hash(config),
        random_seed=0,
        feature_schema_json=_backtest_feature_schema(),
        metrics_json=dict(metrics),
        provenance_json={"engine": "marketlab"},
        status="RESEARCH_ONLY",
    )


def _backtest_feature_schema() -> dict[str, object]:
    return {
        "inputs": ["timestamp", "prediction", "label"],
        "claim_scope": "simulation_only",
    }
