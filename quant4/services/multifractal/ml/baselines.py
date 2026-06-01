"""Local ML baselines for multifractal supervised datasets."""

from __future__ import annotations

from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Protocol

from quant4.services.multifractal.ml.datasets import (
    SupervisedMultifractalRow,
    dataset_matrix,
)

SUPPORTED_SKLEARN_MODELS = (
    "logistic_regression",
    "random_forest",
    "gradient_boosting",
)
SUPPORTED_BASELINE_MODELS = ("majority", *SUPPORTED_SKLEARN_MODELS)


class SklearnClassifier(Protocol):
    """Minimal project-owned interface for optional sklearn classifiers."""

    def fit(
        self,
        features: Sequence[Sequence[float]],
        targets: Sequence[float | str],
    ) -> object:
        """Fit the classifier on dense numeric features."""

    def predict(self, features: Sequence[Sequence[float]]) -> Sequence[object]:
        """Predict labels for dense numeric features."""


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
    if model_name in SUPPORTED_SKLEARN_MODELS:
        return _optional_sklearn_classifier(
            train_rows,
            test_rows,
            target_name,
            model_name,
        )
    expected = SUPPORTED_BASELINE_MODELS
    raise ValueError(
        f"Invalid model_name {model_name!r}; expected one of {expected!r}"
    )


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
    model_name: str,
) -> BaselinePredictionReport:
    try:
        estimator = _sklearn_estimator(model_name)
    except ImportError as exc:
        raise RuntimeError(
            f"Invalid optional model {model_name!r}; expected scikit-learn installed "
            "or model_name='majority'"
        ) from exc
    columns, train_matrix = dataset_matrix(train_rows)
    test_matrix = _matrix_for_columns(test_rows, columns)
    estimator.fit(train_matrix, _target_values(train_rows, target_name))
    return BaselinePredictionReport(
        [_plain_prediction(value) for value in estimator.predict(test_matrix)],
        model_name,
        {"dependency": "scikit-learn", "feature_columns": columns},
    )


def _sklearn_estimator(model_name: str) -> SklearnClassifier:
    if model_name == "logistic_regression":
        from sklearn.linear_model import LogisticRegression

        return LogisticRegression(max_iter=200, random_state=17)
    if model_name == "random_forest":
        from sklearn.ensemble import RandomForestClassifier

        return RandomForestClassifier(n_estimators=50, random_state=17)
    from sklearn.ensemble import GradientBoostingClassifier

    return GradientBoostingClassifier(random_state=17)


def _matrix_for_columns(
    rows: Sequence[SupervisedMultifractalRow],
    columns: Sequence[str],
) -> list[list[float]]:
    return [[row.features.get(column, 0.0) for column in columns] for row in rows]


def _target_values(
    rows: Sequence[SupervisedMultifractalRow],
    target_name: str,
) -> list[float | str]:
    if not rows:
        raise ValueError(f"Invalid train_rows {rows!r}; expected non-empty sequence")
    return [row.targets[target_name] for row in rows]


def _plain_prediction(value: object) -> float | str:
    item = getattr(value, "item", None)
    if callable(item):
        value = item()
    if isinstance(value, int | float):
        return float(value)
    return str(value)


def _majority_target(
    rows: Sequence[SupervisedMultifractalRow],
    target_name: str,
) -> float | str:
    if not rows:
        raise ValueError(f"Invalid train_rows {rows!r}; expected non-empty sequence")
    counts = Counter(row.targets[target_name] for row in rows)
    return counts.most_common(1)[0][0]
