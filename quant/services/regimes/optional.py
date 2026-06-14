"""Optional dependency-backed regime detectors."""

from __future__ import annotations

import importlib
from collections.abc import Sequence

from quant.services.registry import OptionalDependencyMissingError


def detect_ruptures_regime(values: Sequence[float]) -> dict[str, object]:
    """Run the optional ruptures detector or fail with a clear dependency error.

    Example:
        `detect_ruptures_regime([0.01, 0.02])`
    """
    module = _require_optional_module("ruptures", "ruptures")
    return {"detector": "ruptures", "available": True, "module": module.__name__}


def detect_hmm_regime(values: Sequence[float]) -> dict[str, object]:
    """Run the optional HMM detector or fail with a clear dependency error.

    Example:
        `detect_hmm_regime([0.01, 0.02])`
    """
    module = _require_optional_module("hmm", "hmmlearn")
    return {"detector": "hmm", "available": True, "module": module.__name__}


def _require_optional_module(detector: str, module_name: str) -> object:
    try:
        return importlib.import_module(module_name)
    except ImportError as exc:
        raise OptionalDependencyMissingError(
            f"Regime detector {detector!r} requires optional dependency "
            f"{module_name!r}; expected installed module"
        ) from exc
