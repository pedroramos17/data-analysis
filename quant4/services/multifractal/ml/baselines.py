"""Local ML baselines for multifractal supervised datasets."""

from __future__ import annotations

from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass

from quant4.services.multifractal.ml.datasets import SupervisedMultifractalRow


@dataclass(frozen=True, slots=True)
class BaselinePredictionReport:
    """Prediction payload for optional or fallback baseline models.

    Example:
        `report = BaselinePredictionReport([1.0], "majority", {})`
    """

    predictions: list[float | str]
    model_name: str
    metadata: dict[str, object]

    def to_json_dict(self) -> dict[str, object]:
        """Return a JSON-serializable baseline report."""
        return {
            "predictions": self.predictions,
            "model_name": self.model_name,
            "metadata": self.metadata,
            "claims_predictive_performance": False,
        }


def fit_baseline_classifier(
    train_rows: Sequence[SupervisedMultifractalRow],
    test_rows: Sequence[SupervisedMultifractalRow],
    target_name: str,
    model_name: str = "majority",
) -> BaselinePredictionReport:
    """Fit a local classifier baseline and predict test rows.

    Example:
        `report = fit_baseline_classifier(train, test, "next_return_sign")`
    """
    if model_name == "majority":
        return _majority_classifier(train_rows, test_rows, target_name)
    if model_name in {"logistic_regression", "random_forest", "gradient_boosting"}:
        return _optional_sklearn_classifier(train_rows, test_rows, target_name)
    raise ValueError(f"Invalid model_name {model_name!r}; expected baseline name")


def _majority_classifier(
    train_rows: Sequence[SupervisedMultifractalRow],
    test_rows: Sequence[SupervisedMultifractalRow],
    target_name: str,
) -> BaselinePredictionReport:
    majority = _majority_target(train_rows, target_name)
    return BaselinePredictionReport(
        predictions=[majority for _row in test_rows],
        model_name="majority",
        metadata={"dependency": "local_fallback"},
    )


def _optional_sklearn_classifier(
    train_rows: Sequence[SupervisedMultifractalRow],
    test_rows: Sequence[SupervisedMultifractalRow],
    target_name: str,
) -> BaselinePredictionReport:
    try:
        import sklearn  # noqa: F401
    except ImportError:
        return _majority_classifier(train_rows, test_rows, target_name)
    report = _majority_classifier(train_rows, test_rows, target_name)
    return BaselinePredictionReport(
        report.predictions,
        "sklearn_available_placeholder",
        {"dependency": "sklearn_available_not_required"},
    )


def _majority_target(
    rows: Sequence[SupervisedMultifractalRow],
    target_name: str,
) -> float | str:
    if not rows:
        raise ValueError(f"Invalid train_rows {rows!r}; expected non-empty sequence")
    counts = Counter(row.targets[target_name] for row in rows)
    return counts.most_common(1)[0][0]
