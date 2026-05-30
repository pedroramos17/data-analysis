"""Regime run persistence services."""

from __future__ import annotations

from collections.abc import Mapping, Sequence

from quant4.services.regimes.detectors import regime_summary
from quant4.services.registry import stable_config_hash
from sourceflow.config.feature_flags import require_feature


def create_regime_run(
    name: str,
    returns: Sequence[float],
    prices: Sequence[float],
    random_seed: int = 0,
    provenance: Mapping[str, object] | None = None,
) -> object:
    """Persist a local regime detector run.

    Example:
        `create_regime_run("daily", [0.01], [100.0])`
    """
    require_feature("QUANT4_REGIME_CORE")
    from quant4.models import RegimeRun

    config = {"detectors": "mvp2_regime_core", "count": len(returns)}
    return RegimeRun.objects.create(
        name=name,
        component_name="mvp2_regime_core",
        config_json=config,
        config_hash=stable_config_hash(config),
        random_seed=random_seed,
        metrics_json=regime_summary(returns, prices),
        provenance_json=dict(provenance or {}),
        status="RESEARCH_ONLY",
    )
