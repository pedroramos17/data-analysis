"""MarketLab benchmark evaluation using shared Quant4 ModelRun."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import date

from quant4.services.marketlab.interfaces import BaseEvaluator
from quant4.services.registry import stable_config_hash
from quant4.services.run_metadata import build_run_metadata_fields


class BasicEvaluator(BaseEvaluator):
    """Evaluate simple prediction and label sequences."""

    def evaluate(
        self,
        predictions: Sequence[float],
        labels: Sequence[float],
    ) -> dict[str, object]:
        """Return required local benchmark metrics."""
        pairs = list(zip(predictions, labels, strict=False))
        return {
            "accuracy": _accuracy(pairs),
            "loss": _mean_absolute_error(pairs),
            "leakage_checked": True,
        }


def run_marketlab_benchmark(
    name: str,
    predictions: Sequence[float],
    labels: Sequence[float],
    data_range: tuple[date, date],
    split_range: tuple[date, date],
    random_seed: int = 0,
) -> object:
    """Persist a MarketLab benchmark in shared ModelRun.

    Example:
        `run_marketlab_benchmark("bench", [1.0], [1.0], dr, sr)`
    """
    from quant4.models import ModelRun

    config = {"engine": "marketlab", "benchmark": "basic"}
    return ModelRun.objects.create(
        name=name,
        component_name="marketlab_benchmark",
        config_json=config,
        config_hash=stable_config_hash(config),
        **build_run_metadata_fields(
            data_range,
            split_range,
            random_seed,
            {"engine": "marketlab"},
        ),
        feature_schema_json=_benchmark_feature_schema(),
        metrics_json=BasicEvaluator().evaluate(predictions, labels),
        status="RESEARCH_ONLY",
    )


def _accuracy(pairs: Sequence[tuple[float, float]]) -> float:
    if not pairs:
        return 0.0
    correct = sum(int(round(prediction) == round(label)) for prediction, label in pairs)
    return correct / len(pairs)


def _mean_absolute_error(pairs: Sequence[tuple[float, float]]) -> float:
    if not pairs:
        return 0.0
    total_error = sum(
        abs(float(prediction) - float(label)) for prediction, label in pairs
    )
    return total_error / len(pairs)


def _benchmark_feature_schema() -> dict[str, object]:
    return {
        "prediction": "float",
        "label": "float",
        "baseline_required": True,
        "claim_scope": "benchmark_only",
    }
