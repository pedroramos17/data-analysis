"""Phase 8 evaluation pipeline runner."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path

from src.config.settings import load_runtime_settings
from src.pipeline.evaluation.backtester import register_backtest_metrics, run_backtest_from_predictions
from src.pipeline.evaluation.evaluator import (
    aggregate_metrics,
    evaluate_predictions,
    feature_drift,
    prediction_drift,
    regime_conditional_metrics,
    register_evaluation_metrics,
)
from src.pipeline.evaluation.predictor import baseline_predictions, predict_window
from src.pipeline.evaluation.risk_report import compute_risk_report
from src.pipeline.evaluation.window_report import write_aggregate_report, write_window_report
from src.pipeline.features.base import read_feature_input_rows
from src.providers.registry import ProviderRegistry, build_provider_registry


@dataclass(frozen=True, slots=True)
class WindowEvaluationResult:
    """Per-window evaluation result."""

    window_id: int
    prediction_output: dict[str, object]
    metrics: dict[str, object]
    backtest: dict[str, object]
    risk: dict[str, object]
    drift: dict[str, object]
    reports: dict[str, str]

    def to_dict(self) -> dict[str, object]:
        return {
            "window_id": self.window_id,
            "prediction_output": dict(self.prediction_output),
            "metrics": dict(self.metrics),
            "backtest": dict(self.backtest),
            "risk": dict(self.risk),
            "drift": dict(self.drift),
            "reports": dict(self.reports),
        }


@dataclass(frozen=True, slots=True)
class EvaluationPipelineResult:
    """Top-level Phase 8 evaluation result."""

    status: str
    model_name: str
    model_version: str
    windows: list[WindowEvaluationResult]
    aggregate_report: dict[str, object]
    reports: dict[str, str]
    database_records: dict[str, object] = field(default_factory=dict)

    def to_dict(self) -> dict[str, object]:
        return {
            "status": self.status,
            "model_name": self.model_name,
            "model_version": self.model_version,
            "windows": [window.to_dict() for window in self.windows],
            "aggregate_report": dict(self.aggregate_report),
            "reports": dict(self.reports),
            "database_records": dict(self.database_records),
        }


def run_evaluation(
    config: Mapping[str, object],
    registry: ProviderRegistry | None = None,
) -> EvaluationPipelineResult:
    """Run Phase 8 evaluation over every sliding-window dataset partition."""
    active_registry = registry or build_provider_registry(load_runtime_settings())
    lake_root = _config_path(config, "lake_root", active_registry.settings.storage.local_root)
    dataset_root = _config_path(config, "dataset_path", lake_root / "datasets")
    model_root = _config_path(config, "model_root", lake_root / "models")
    report_root = _config_path(config, "report_root", lake_root / "reports" / "evaluation")
    prediction_root = str(config.get("prediction_root") or "predictions")
    model_name = str(config.get("model_name") or "naive_return")
    model_version = str(config.get("model_version") or config.get("version") or "phase8_v1")
    dataset_name = str(config.get("dataset_name") or "default")
    dataset_version = str(config.get("dataset_version") or config.get("version") or "phase6_v1")
    target_column = str(config.get("target_column") or "target")
    horizon = config.get("horizon", config.get("horizon_days", "1d"))
    windows = _window_dirs(dataset_root, dataset_name, dataset_version, config)
    results: list[WindowEvaluationResult] = []
    database_records: dict[str, object] = {}

    for window_dir in windows:
        window_result = _evaluate_window(
            window_dir,
            config,
            active_registry,
            model_name=model_name,
            model_version=model_version,
            model_root=model_root,
            report_root=report_root,
            prediction_root=prediction_root,
            target_column=target_column,
            horizon=horizon,
        )
        results.append(window_result)

    aggregate = _aggregate_report(config, model_name, model_version, results)
    reports = write_aggregate_report(aggregate, report_root / f"model={_token(model_name)}" / f"version={_token(model_version)}")
    if _bool(config.get("store_metrics"), True):
        database_records["evaluation_run_id"] = register_evaluation_metrics(
            active_registry.settings.database,
            str(config.get("name") or f"evaluation_{model_name}_{model_version}"),
            config,
            aggregate,
        )
    return EvaluationPipelineResult(
        status="COMPLETED" if results else "NO_WINDOWS",
        model_name=model_name,
        model_version=model_version,
        windows=results,
        aggregate_report=aggregate,
        reports=reports,
        database_records=database_records,
    )


def run_backtest_from_config(
    config: Mapping[str, object],
    registry: ProviderRegistry | None = None,
) -> dict[str, object]:
    """Run Phase 8 backtest directly from a predictions path."""
    active_registry = registry or build_provider_registry(load_runtime_settings())
    predictions_path = config.get("predictions_path") or config.get("prediction_path")
    if not predictions_path:
        raise ValueError("Phase 8 backtest requires predictions_path")
    rows, _reader, _uri = read_feature_input_rows(predictions_path, require_duckdb=_bool(config.get("require_duckdb"), False))
    metrics = run_backtest_from_predictions(rows, config)
    run_id = register_backtest_metrics(
        active_registry.settings.database,
        str(config.get("name") or "phase8_backtest"),
        config,
        metrics,
    )
    return {"status": "COMPLETED", "metrics": metrics, "database_record_id": run_id}


def _evaluate_window(
    window_dir: Path,
    config: Mapping[str, object],
    registry: ProviderRegistry,
    *,
    model_name: str,
    model_version: str,
    model_root: Path,
    report_root: Path,
    prediction_root: str,
    target_column: str,
    horizon: object,
) -> WindowEvaluationResult:
    window_id = _window_id(window_dir)
    train_rows, _train_reader, _train_uri = read_feature_input_rows(window_dir / "train.parquet", require_duckdb=_bool(config.get("require_duckdb"), False))
    validation_rows, _val_reader, _val_uri = read_feature_input_rows(window_dir / "validation.parquet", require_duckdb=_bool(config.get("require_duckdb"), False))
    test_rows, _test_reader, _test_uri = read_feature_input_rows(window_dir / "test.parquet", require_duckdb=_bool(config.get("require_duckdb"), False))
    eval_rows = validation_rows + test_rows
    model_path = _model_path(model_root, model_name, window_id, config)
    prediction_key = (
        f"{prediction_root}/model={_token(model_name)}/version={_token(model_version)}/"
        f"window_id={window_id}/predictions.parquet"
    )
    prediction = predict_window(
        train_rows,
        eval_rows,
        model_name=model_name,
        model_version=model_version,
        model_path=model_path,
        window_id=window_id,
        horizon=horizon,
        target_column=target_column,
        registry=registry,
        output_key=prediction_key,
    )
    baseline_rows = baseline_predictions(train_rows, eval_rows, target_column=target_column, horizon=horizon)
    comparison = evaluate_predictions(
        prediction.rows,
        baseline_rows,
        latency_seconds=prediction.latency_seconds,
        gpu_hourly_cost=float(config.get("gpu_hourly_cost") or 0.0),
    )
    backtest = run_backtest_from_predictions(prediction.rows, config)
    risk = compute_risk_report(prediction.rows).to_dict()
    drift = {
        "feature_drift": feature_drift(train_rows, eval_rows),
        "prediction_drift": prediction_drift(prediction.rows),
        "regime_conditional_metrics": regime_conditional_metrics(prediction.rows),
    }
    report = {
        "window_id": window_id,
        "model_name": model_name,
        "model_version": model_version,
        "prediction_output": prediction.to_dict(),
        "metrics": comparison.to_dict(),
        "backtest": backtest,
        "risk": risk,
        "drift": drift,
    }
    reports = write_window_report(
        report,
        report_root / f"model={_token(model_name)}" / f"version={_token(model_version)}" / f"window_id={window_id}",
    )
    return WindowEvaluationResult(
        window_id=window_id,
        prediction_output=prediction.to_dict(),
        metrics=comparison.to_dict(),
        backtest=backtest,
        risk=risk,
        drift=drift,
        reports=reports,
    )


def _aggregate_report(
    config: Mapping[str, object],
    model_name: str,
    model_version: str,
    windows: Sequence[WindowEvaluationResult],
) -> dict[str, object]:
    per_window = [window.metrics for window in windows]
    aggregate = aggregate_metrics(per_window)
    return {
        "model_name": model_name,
        "model_version": model_version,
        "windows": len(windows),
        "per_window_metrics": per_window,
        "aggregate_metrics": aggregate.get("aggregate_metrics", {}),
        "stability_metrics": aggregate.get("stability_metrics", {}),
        "regime_conditional_metrics": _merge_nested([window.drift.get("regime_conditional_metrics", {}) for window in windows]),
        "feature_drift": _merge_nested([window.drift.get("feature_drift", {}) for window in windows]),
        "prediction_drift": _merge_nested([window.drift.get("prediction_drift", {}) for window in windows]),
        "latency": _latency(windows),
        "cost_estimate": _cost_estimate(windows, config),
        "warnings": aggregate.get("warnings", []),
        "model_better_than_baseline_rate": aggregate.get("model_better_than_baseline_rate", 0.0),
        "model_not_better_than_baseline": any(window.metrics.get("warning") for window in windows),
    }


def _window_dirs(dataset_root: Path, dataset_name: str, dataset_version: str, config: Mapping[str, object]) -> list[Path]:
    configured = config.get("window_path") or config.get("dataset_window_path")
    if configured:
        return [Path(str(configured))]
    base = dataset_root / f"dataset={dataset_name}" / f"version={dataset_version}"
    if base.exists():
        return sorted(path for path in base.iterdir() if path.is_dir() and path.name.startswith("window_id="))
    fallback = dataset_root / f"dataset={dataset_name}"
    if fallback.exists():
        return sorted(path for path in fallback.iterdir() if path.is_dir() and path.name.startswith("window_id="))
    return []


def _model_path(model_root: Path, model_name: str, window_id: int, config: Mapping[str, object]) -> Path | None:
    configured = config.get("model_path")
    if configured:
        return Path(str(configured))
    candidates = [
        model_root / model_name / f"window_{window_id}" / f"{model_name}.json",
        model_root / model_name / f"{model_name}.json",
        model_root / f"{model_name}.json",
    ]
    return next((path for path in candidates if path.exists()), None)


def _window_id(path: Path) -> int:
    try:
        return int(path.name.split("=", 1)[1])
    except (IndexError, ValueError):
        return 0


def _latency(windows: Sequence[WindowEvaluationResult]) -> dict[str, float]:
    values = [float(window.prediction_output.get("latency_seconds") or 0.0) for window in windows]
    return {"total_seconds": sum(values), "mean_seconds": sum(values) / max(len(values), 1)}


def _cost_estimate(windows: Sequence[WindowEvaluationResult], config: Mapping[str, object]) -> dict[str, float]:
    hourly = float(config.get("gpu_hourly_cost") or 0.0)
    seconds = _latency(windows)["total_seconds"]
    return {"estimated_usd": seconds / 3600.0 * hourly, "gpu_hourly_cost": hourly}


def _merge_nested(values: Sequence[object]) -> dict[str, object]:
    merged: dict[str, object] = {}
    for value in values:
        if not isinstance(value, Mapping):
            continue
        for key, item in value.items():
            merged.setdefault(str(key), []).append(item)
    return merged


def _config_path(config: Mapping[str, object], key: str, default: Path) -> Path:
    value = config.get(key)
    if value in (None, ""):
        return default
    return Path(str(value))


def _bool(value: object, default: bool) -> bool:
    if value in (None, ""):
        return default
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


def _token(value: str) -> str:
    return "".join(char if char.isalnum() or char in "-_" else "_" for char in str(value)).strip("_") or "unnamed"
