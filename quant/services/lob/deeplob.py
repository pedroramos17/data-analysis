"""Local LOB baselines and optional deep-learning model stubs."""

from __future__ import annotations

import importlib
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from quant.services.registry import OptionalDependencyMissingError
from sourceflow.config.feature_flags import require_feature


@dataclass(frozen=True, slots=True)
class NaiveImbalanceBaseline:
    """Predict direction from order imbalance without optional dependencies.

    Example:
        `NaiveImbalanceBaseline().predict([{"order_imbalance": 0.2}])`
    """

    threshold: float = 0.0

    def predict(self, rows: Sequence[Mapping[str, float]]) -> list[int]:
        """Return -1, 0, or 1 from each row's order imbalance."""
        return [
            _imbalance_signal(row.get("order_imbalance", 0.0), self.threshold)
            for row in rows
        ]


@dataclass(slots=True)
class LogisticRegressionBaseline:
    """Tiny local logistic-style baseline using a learned imbalance cutoff."""

    threshold: float = 0.0

    def fit(
        self,
        rows: Sequence[Mapping[str, float]],
        labels: Sequence[int],
    ) -> LogisticRegressionBaseline:
        """Fit a deterministic imbalance threshold."""
        positives = _imbalances_for_label(rows, labels, 1)
        negatives = _imbalances_for_label(rows, labels, -1)
        self.threshold = _midpoint(_mean(positives), _mean(negatives))
        return self

    def predict(self, rows: Sequence[Mapping[str, float]]) -> list[int]:
        """Return baseline direction predictions."""
        return [
            _imbalance_signal(row.get("order_imbalance", 0.0), self.threshold)
            for row in rows
        ]


@dataclass(frozen=True, slots=True)
class DeepLOBModel:
    """Optional PyTorch-backed DeepLOB placeholder."""

    required_module: str = "torch"

    def fit(self) -> None:
        """Fail clearly unless DeepLOB dependencies and flag are enabled."""
        require_feature("QUANT_LOB_DEEPLOB")
        _require_torch_backend("deeplob", self.required_module)


@dataclass(frozen=True, slots=True)
class TCNLOBModel:
    """Optional PyTorch-backed TCN-LOB placeholder."""

    required_module: str = "torch"

    def fit(self) -> None:
        """Fail clearly unless TCN-LOB dependencies and flag are enabled."""
        require_feature("QUANT_LOB_TCN")
        _require_torch_backend("tcn_lob", self.required_module)


def _imbalance_signal(value: float, threshold: float) -> int:
    if value > threshold:
        return 1
    if value < -threshold:
        return -1
    return 0


def _require_torch_backend(component: str, module_name: str) -> None:
    try:
        importlib.import_module(module_name)
    except ImportError as exc:
        raise OptionalDependencyMissingError(
            f"Component {component!r} requires optional dependency "
            f"{module_name!r}; expected installed module"
        ) from exc


def _mean(values: Sequence[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def _midpoint(left_value: float, right_value: float) -> float:
    return (left_value + right_value) / 2.0


def _imbalances_for_label(
    rows: Sequence[Mapping[str, float]],
    labels: Sequence[int],
    target_label: int,
) -> list[float]:
    return [
        row["order_imbalance"]
        for row, label in zip(rows, labels, strict=False)
        if label == target_label
    ]
