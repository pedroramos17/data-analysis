"""Baseline finance models without mandatory heavy dependencies."""

from __future__ import annotations

from collections.abc import Sequence

from sourceflow.config.feature_flags import require_feature


def fit_ridge_baseline(
    features: Sequence[Sequence[float]],
    targets: Sequence[float],
) -> dict[str, object]:
    """Fit a small ridge baseline or return a pure-Python mean model.

    Example:
        `model = fit_ridge_baseline([[1.0]], [0.1])`
    """
    require_feature("FIN_MODEL_BASELINE")
    try:
        return _sklearn_ridge(features, targets)
    except ImportError:
        return _mean_model(targets)


def predict_baseline(
    model: dict[str, object], rows: Sequence[Sequence[float]]
) -> list[float]:
    """Predict with the baseline model wrapper.

    Example:
        `preds = predict_baseline(model, [[1.0]])`
    """
    estimator = model.get("estimator")
    if estimator is not None:
        return list(estimator.predict(rows))
    return [float(model["mean_target"]) for _row in rows]


def _sklearn_ridge(
    features: Sequence[Sequence[float]],
    targets: Sequence[float],
) -> dict[str, object]:
    from sklearn.linear_model import Ridge

    estimator = Ridge(alpha=1.0).fit(features, targets)
    return {"model_type": "sklearn_ridge", "estimator": estimator}


def _mean_model(targets: Sequence[float]) -> dict[str, object]:
    mean_target = sum(float(value) for value in targets) / max(len(targets), 1)
    return {"model_type": "mean_baseline", "mean_target": mean_target}
