"""LOB baseline training, evaluation, and LOBRun persistence."""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

from quant.services.lob.deeplob import (
    LogisticRegressionBaseline,
    NaiveImbalanceBaseline,
)
from quant.services.lob.microstructure_labels import LOBLabelRow, build_lob_labels
from quant.services.lob.orderbook_features import (
    OrderBookFeatureRow,
    build_orderbook_features,
)
from quant.services.lob.parser import LOBSnapshot, parse_lob_jsonl
from quant.services.registry import stable_config_hash
from quant.services.run_metadata import DateRange, build_run_metadata_fields
from sourceflow.config.feature_flags import require_feature


@dataclass(frozen=True, slots=True)
class LOBTrainingResult:
    """Serializable LOB baseline training output.

    Example:
        `LOBTrainingResult({"accuracy": 1.0}, {}, {})`
    """

    metrics: dict[str, object]
    artifact_paths: dict[str, str]
    feature_schema: dict[str, object]


def train_lob_baseline_run(
    name: str,
    input_path: str,
    output_dir: str,
    data_range: DateRange,
    split_range: DateRange,
    model_name: str = "naive_imbalance",
    horizon: int = 1,
    random_seed: int = 0,
) -> object:
    """Train a local LOB baseline and persist an LOBRun."""
    require_feature("QUANT_LOB_CORE")
    snapshots = parse_lob_jsonl(input_path)
    result = train_lob_baseline(name, snapshots, output_dir, model_name, horizon)
    return _persist_lob_run(
        name, result, data_range, split_range, model_name, horizon, random_seed
    )


def train_lob_baseline(
    name: str,
    snapshots: Sequence[LOBSnapshot],
    output_dir: str,
    model_name: str = "naive_imbalance",
    horizon: int = 1,
) -> LOBTrainingResult:
    """Train a dependency-light LOB baseline and write artifacts."""
    features = build_orderbook_features(snapshots)
    labels = build_lob_labels(snapshots, horizon=horizon)
    predictions = _predict(model_name, features, labels)
    metrics = evaluate_lob_predictions(predictions, _directions(labels))
    paths = _write_lob_artifacts(name, output_dir, features, predictions, metrics)
    return LOBTrainingResult(metrics | {"artifact_paths": paths}, paths, _schema())


def evaluate_lob_predictions(
    predictions: Sequence[int],
    labels: Sequence[int],
) -> dict[str, object]:
    """Return deterministic classification metrics for LOB baselines.

    Example:
        `evaluate_lob_predictions([1], [1])`
    """
    if len(predictions) != len(labels):
        raise ValueError(
            f"Invalid predictions {len(predictions)!r}; expected {len(labels)} labels"
        )
    correct = sum(
        int(prediction == label)
        for prediction, label in zip(predictions, labels, strict=True)
    )
    total = max(len(labels), 1)
    return {"accuracy": correct / total, "sample_count": len(labels)}


def _predict(
    model_name: str,
    features: Sequence[OrderBookFeatureRow],
    labels: Sequence[LOBLabelRow],
) -> list[int]:
    rows = [row.values for row in features]
    if model_name == "naive_imbalance":
        return NaiveImbalanceBaseline().predict(rows)
    if model_name == "logistic_regression":
        directions = _directions(labels)
        return LogisticRegressionBaseline().fit(rows, directions).predict(rows)
    raise ValueError(
        f"Invalid LOB model {model_name!r}; "
        "expected naive_imbalance or logistic_regression"
    )


def _directions(labels: Sequence[LOBLabelRow]) -> list[int]:
    return [int(label.values["h_step_direction"]) for label in labels]


def _persist_lob_run(
    name: str,
    result: LOBTrainingResult,
    data_range: DateRange,
    split_range: DateRange,
    model_name: str,
    horizon: int,
    random_seed: int,
) -> object:
    from quant.models import LOBRun

    config = {"engine": "quant_lob", "model": model_name, "horizon": horizon}
    return LOBRun.objects.create(
        name=name,
        component_name="quant_lob",
        config_json=config,
        config_hash=stable_config_hash(config),
        artifact_uri=result.artifact_paths["metrics_path"],
        metrics_json=result.metrics,
        feature_schema_json=result.feature_schema,
        status="RESEARCH_ONLY",
        **build_run_metadata_fields(data_range, split_range, random_seed, config),
    )


def _write_lob_artifacts(
    name: str,
    output_dir: str,
    features: Sequence[OrderBookFeatureRow],
    predictions: Sequence[int],
    metrics: Mapping[str, object],
) -> dict[str, str]:
    root = Path(output_dir)
    root.mkdir(parents=True, exist_ok=True)
    paths = _artifact_paths(root, name)
    feature_payloads = [_feature_payload(row) for row in features]
    _write_json(paths["features_path"], {"features": feature_payloads})
    _write_json(paths["predictions_path"], {"predictions": list(predictions)})
    _write_json(paths["metrics_path"], {"metrics": dict(metrics)})
    return paths


def _artifact_paths(root: Path, name: str) -> dict[str, str]:
    safe_name = "".join(
        char if char.isalnum() or char in "-_" else "_" for char in name
    )
    return {
        "features_path": str(root / f"{safe_name}_lob_features.json"),
        "predictions_path": str(root / f"{safe_name}_lob_predictions.json"),
        "metrics_path": str(root / f"{safe_name}_lob_metrics.json"),
    }


def _feature_payload(row: OrderBookFeatureRow) -> dict[str, object]:
    return {"timestamp": row.timestamp, "symbol": row.symbol, "values": row.values}


def _write_json(path: str, payload: Mapping[str, object]) -> None:
    Path(path).write_text(json.dumps(payload, sort_keys=True), encoding="utf-8")


def _schema() -> dict[str, object]:
    return {
        "inputs": "normalized_lob_snapshots",
        "features": "past_only_microstructure_features",
        "labels": "horizon_aware_microstructure_labels",
        "claim_scope": "research_only_no_execution",
    }
