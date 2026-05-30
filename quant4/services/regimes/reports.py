"""Regime run persistence services."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import date

from quant4.services.regimes.detectors import regime_summary
from quant4.services.registry import stable_config_hash
from quant4.services.run_metadata import build_run_metadata_fields
from sourceflow.config.feature_flags import require_feature


def create_regime_run(
    name: str,
    returns: Sequence[float],
    prices: Sequence[float],
    data_range: tuple[date, date],
    split_range: tuple[date, date],
    random_seed: int = 0,
    provenance: Mapping[str, object] | None = None,
) -> object:
    """Persist a local regime detector run.

    Example:
        `create_regime_run("daily", [0.01], [100.0], dr, sr)`
    """
    require_feature("QUANT4_REGIME_CORE")
    from quant4.models import RegimeRun

    config = {"detectors": "mvp2_regime_core", "count": len(returns)}
    return RegimeRun.objects.create(
        name=name,
        component_name="mvp2_regime_core",
        config_json=config,
        config_hash=stable_config_hash(config),
        **build_run_metadata_fields(data_range, split_range, random_seed, provenance),
        feature_schema_json=_regime_feature_schema(),
        metrics_json=regime_summary(returns, prices),
        status="RESEARCH_ONLY",
    )


def _regime_feature_schema() -> dict[str, object]:
    return {
        "returns": "past_sequence_float",
        "prices": "past_sequence_float",
        "fit_scope": "training_or_past_only",
    }
