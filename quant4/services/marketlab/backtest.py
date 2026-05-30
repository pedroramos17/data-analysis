"""MarketLab backtest metadata helpers."""

from __future__ import annotations

from datetime import date

from quant4.services.registry import stable_config_hash
from quant4.services.run_metadata import build_run_metadata_fields


def create_backtest_run(
    name: str,
    metrics: dict[str, object],
    data_range: tuple[date, date],
    split_range: tuple[date, date],
    random_seed: int = 0,
) -> object:
    """Persist a research-only backtest run through shared Quant4 models.

    Example:
        `create_backtest_run("wf", {"loss": 0.1}, dr, sr)`
    """
    from quant4.models import BacktestRun

    config = {"engine": "marketlab", "mode": "research_backtest"}
    return BacktestRun.objects.create(
        name=name,
        component_name="marketlab_backtest",
        config_json=config,
        config_hash=stable_config_hash(config),
        **build_run_metadata_fields(
            data_range,
            split_range,
            random_seed,
            {"engine": "marketlab"},
        ),
        feature_schema_json=_backtest_feature_schema(),
        metrics_json=dict(metrics),
        status="RESEARCH_ONLY",
    )


def _backtest_feature_schema() -> dict[str, object]:
    return {
        "inputs": ["timestamp", "prediction", "label"],
        "claim_scope": "simulation_only",
    }
