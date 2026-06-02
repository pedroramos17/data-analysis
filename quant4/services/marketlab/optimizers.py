"""MarketLab optimizer factory."""

from __future__ import annotations

from dataclasses import dataclass

from quant4.services.marketlab.interfaces import BaseOptimizerFactory
from sourceflow.config.feature_flags import require_feature

LOCAL_OPTIMIZERS = frozenset({"Adam", "AdamW", "AdaGrad"})
OPTIONAL_FLAGS = {
    "Lion": "QUANT4_MARKETLAB_OPTIMIZER_LION",
    "Sophia": "QUANT4_MARKETLAB_OPTIMIZER_SOPHIA",
    "Muon": "QUANT4_MARKETLAB_OPTIMIZER_MUON",
    "SpecMuon": "QUANT4_MARKETLAB_OPTIMIZER_SPECMUON",
}


@dataclass(frozen=True, slots=True)
class OptimizerConfig:
    """Optimizer config without framework dependency."""

    name: str
    config: dict[str, object]


class OptimizerFactory(BaseOptimizerFactory):
    """Return dependency-free optimizer configs."""

    def create(self, name: str, learning_rate: float = 0.001) -> OptimizerConfig:
        """Create a local optimizer config or require an optional flag."""
        normalized = _normalized_name(name)
        _require_optimizer_available(normalized)
        return OptimizerConfig(normalized, {"learning_rate": learning_rate})


def _normalized_name(name: str) -> str:
    mapping = {"adagrad": "AdaGrad", "adam": "Adam", "adamw": "AdamW"}
    return mapping.get(name.lower(), name)


def _require_optimizer_available(name: str) -> None:
    if name in LOCAL_OPTIMIZERS:
        return
    if name in OPTIONAL_FLAGS:
        require_feature(OPTIONAL_FLAGS[name])
        return
    expected = sorted(LOCAL_OPTIMIZERS | frozenset(OPTIONAL_FLAGS))
    raise ValueError(f"Invalid optimizer {name!r}; expected one of {expected}")
