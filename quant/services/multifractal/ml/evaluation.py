"""Walk-forward evaluation for multifractal ML baselines."""

from __future__ import annotations

from collections.abc import Sequence

from quant.services.multifractal.ml.baselines import fit_baseline_classifier
from quant.services.multifractal.ml.datasets import (
    SupervisedMultifractalRow,
    build_walk_forward_splits,
)


def evaluate_walk_forward(
    rows: Sequence[SupervisedMultifractalRow],
    target_name: str,
    train_size: int,
    test_size: int,
    purge_gap: int = 0,
    model_name: str = "majority",
) -> dict[str, object]:
    """Evaluate a baseline using non-random walk-forward splits."""
    splits = build_walk_forward_splits(len(rows), train_size, test_size, purge_gap)
    split_reports = [
        _evaluate_split(
            rows,
            split.train_indices,
            split.test_indices,
            target_name,
            model_name,
        )
        for split in splits
    ]
    return {
        "validation_method": "walk_forward",
        "model_name": model_name,
        "splits": split_reports,
        "aggregate": _aggregate(split_reports),
        "claims_predictive_performance": False,
    }


def classification_metrics(
    true_values: Sequence[float | str],
    predictions: Sequence[float | str],
) -> dict[str, float]:
    """Return accuracy and binary F1 where labels permit."""
    if len(true_values) != len(predictions):
        raise ValueError(
            f"Invalid prediction lengths {(len(true_values), len(predictions))!r}; "
            "expected equal lengths"
        )
    accuracy = _accuracy(true_values, predictions)
    return {"accuracy": accuracy, "f1": _binary_f1(true_values, predictions)}


def _evaluate_split(
    rows: Sequence[SupervisedMultifractalRow],
    train_indices: Sequence[int],
    test_indices: Sequence[int],
    target_name: str,
    model_name: str,
) -> dict[str, object]:
    train = [rows[index] for index in train_indices]
    test = [rows[index] for index in test_indices]
    report = fit_baseline_classifier(train, test, target_name, model_name)
    truth = [row.targets[target_name] for row in test]
    return {
        "train_start": train_indices[0],
        "train_end": train_indices[-1],
        "test_start": test_indices[0],
        "test_end": test_indices[-1],
        "metrics": classification_metrics(truth, report.predictions),
    }


def _aggregate(split_reports: Sequence[dict[str, object]]) -> dict[str, float]:
    if not split_reports:
        return {"accuracy": 0.0, "f1": 0.0}
    metrics = [report["metrics"] for report in split_reports]
    return {
        "accuracy": _mean_metric(metrics, "accuracy"),
        "f1": _mean_metric(metrics, "f1"),
    }


def _mean_metric(metrics: Sequence[object], key: str) -> float:
    values = [float(metric[key]) for metric in metrics if isinstance(metric, dict)]
    return sum(values) / len(values) if values else 0.0


def _accuracy(
    true_values: Sequence[float | str],
    predictions: Sequence[float | str],
) -> float:
    if not true_values:
        return 0.0
    hits = sum(
        1
        for left, right in zip(true_values, predictions, strict=True)
        if left == right
    )
    return hits / len(true_values)


def _binary_f1(
    true_values: Sequence[float | str],
    predictions: Sequence[float | str],
) -> float:
    positives = {1.0, "1", "positive"}
    tp = _count_pair(true_values, predictions, positives, positives)
    fp = _count_pair(true_values, predictions, set(true_values) - positives, positives)
    fn = _count_pair(true_values, predictions, positives, set(predictions) - positives)
    denominator = (2 * tp) + fp + fn
    return (2 * tp) / denominator if denominator else 0.0


def _count_pair(
    true_values: Sequence[float | str],
    predictions: Sequence[float | str],
    true_set: set[float | str],
    prediction_set: set[float | str],
) -> int:
    return sum(
        1
        for left, right in zip(true_values, predictions, strict=True)
        if left in true_set and right in prediction_set
    )
