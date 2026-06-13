"""Task handlers for the orchestrated MVP pipeline DAG."""

from __future__ import annotations

import json
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from src.pipeline.evaluation import run_backtest_from_config, run_evaluation
from src.pipeline.features import run_feature_pipeline
from src.pipeline.ingestion import run_ingestion
from src.pipeline.preprocessing import run_preprocessing
from src.pipeline.training import run_training
from src.pipeline.windows import build_dataset
from src.providers.registry import ProviderRegistry
from src.workflows import run_mvp_demo

TaskHandler = Callable[["TaskContext"], "TaskResult"]


@dataclass(frozen=True, slots=True)
class TaskContext:
    """Runtime context passed to one pipeline task."""

    run_id: int
    run_name: str
    task_name: str
    config: Mapping[str, object]
    artifacts: Mapping[str, str]
    registry: ProviderRegistry

    @property
    def lake_root(self) -> Path:
        """Return configured local lake root."""
        return Path(self.registry.settings.storage.local_root)


@dataclass(frozen=True, slots=True)
class TaskResult:
    """Result from one pipeline task."""

    status: str = "COMPLETED"
    output_uri: str = ""
    artifacts: dict[str, str] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, object]:
        """Return a JSON-friendly result."""
        return {
            "status": self.status,
            "output_uri": self.output_uri,
            "artifacts": dict(self.artifacts),
            "metadata": dict(self.metadata),
        }


def default_task_handlers() -> dict[str, TaskHandler]:
    """Return default handlers for the Phase 12 DAG."""
    return {
        "ingest_raw": ingest_raw,
        "preprocess": preprocess,
        "extract_features": extract_features,
        "build_sliding_windows": build_sliding_windows,
        "train_baselines": train_baselines,
        "train_neural_optional": train_neural_optional,
        "predict": predict,
        "evaluate": evaluate,
        "backtest": backtest,
        "risk_report": risk_report,
        "aggregate_report": aggregate_report,
    }


def ingest_raw(context: TaskContext) -> TaskResult:
    """Run or mark raw ingestion."""
    config = _task_config(context, "ingest_raw", "ingest")
    if config:
        result = run_ingestion(config, context.registry).to_dict()
        return _result_from_payload(context, "ingest_raw", result)
    return _marker(context, {"task": "ingest_raw", "mode": "marker"})


def preprocess(context: TaskContext) -> TaskResult:
    """Run or mark preprocessing."""
    config = _task_config(context, "preprocess", "preprocessing")
    if config:
        result = run_preprocessing(config, context.registry).to_dict()
        return _result_from_payload(context, "preprocess", result)
    return _marker(context, {"task": "preprocess", "input_artifacts": dict(context.artifacts)})


def extract_features(context: TaskContext) -> TaskResult:
    """Run or mark feature extraction."""
    config = _task_config(context, "extract_features", "features")
    if config:
        result = run_feature_pipeline(config, context.registry).to_dict()
        return _result_from_payload(context, "extract_features", result)
    return _marker(context, {"task": "extract_features", "input_artifacts": dict(context.artifacts)})


def build_sliding_windows(context: TaskContext) -> TaskResult:
    """Run or mark sliding-window dataset construction."""
    config = _task_config(context, "build_sliding_windows", "sliding_windows", "windows")
    if config:
        result = build_dataset(config, context.registry).to_dict()
        return _result_from_payload(context, "build_sliding_windows", result)
    return _marker(context, {"task": "build_sliding_windows", "input_artifacts": dict(context.artifacts)})


def train_baselines(context: TaskContext) -> TaskResult:
    """Run or mark baseline training."""
    config = _task_config(context, "train_baselines", "train", "training")
    if config:
        result = run_training(config, context.registry).to_dict()
        return _result_from_payload(context, "train_baselines", result)
    return _marker(context, {"task": "train_baselines", "input_artifacts": dict(context.artifacts)})


def train_neural_optional(context: TaskContext) -> TaskResult:
    """Run optional neural training when explicitly enabled."""
    config = _task_config(context, "train_neural_optional", "train_neural", "neural_training")
    if not _enabled(config):
        return _marker(
            context,
            {"task": "train_neural_optional", "status": "SKIPPED", "reason": "not enabled"},
            status="SKIPPED",
        )
    result = run_training(config, context.registry).to_dict()
    return _result_from_payload(context, "train_neural_optional", result)


def predict(context: TaskContext) -> TaskResult:
    """Record prediction stage output or defer to evaluation pipeline."""
    config = _task_config(context, "predict", "prediction")
    if config.get("mode") == "evaluation":
        result = run_evaluation(config, context.registry).to_dict()
        return _result_from_payload(context, "predict", result)
    return _marker(context, {"task": "predict", "input_artifacts": dict(context.artifacts)})


def evaluate(context: TaskContext) -> TaskResult:
    """Run evaluation when configured, otherwise record the stage."""
    config = _task_config(context, "evaluate", "evaluation")
    if config:
        result = run_evaluation(config, context.registry).to_dict()
        return _result_from_payload(context, "evaluate", result)
    return _marker(context, {"task": "evaluate", "input_artifacts": dict(context.artifacts)})


def backtest(context: TaskContext) -> TaskResult:
    """Run configured backtest or record stage artifact."""
    config = _task_config(context, "backtest")
    if config:
        result = run_backtest_from_config(config, context.registry)
        return _result_from_payload(context, "backtest", result)
    return _marker(context, {"task": "backtest", "input_artifacts": dict(context.artifacts)})


def risk_report(context: TaskContext) -> TaskResult:
    """Record risk stage artifact."""
    config = _task_config(context, "risk_report", "risk")
    return _marker(context, {"task": "risk_report", "config": config, "input_artifacts": dict(context.artifacts)})


def aggregate_report(context: TaskContext) -> TaskResult:
    """Aggregate pipeline artifacts and run the local MVP workflow by default."""
    config = _task_config(context, "aggregate_report", "mvp_demo")
    if _enabled(config, default=True):
        try:
            result = run_mvp_demo(config or {}, settings=context.registry.settings).to_dict()
        except ModuleNotFoundError as exc:
            result = {
                "run_id": context.run_name,
                "status": "COMPLETED_FALLBACK",
                "reason": f"optional dependency unavailable: {exc}",
                "artifacts": dict(context.artifacts),
            }
        output_uri = str(result.get("report_uri") or result.get("report_path") or "")
        if not output_uri:
            output_uri = _write_marker(context, "aggregate_report", result)
        return TaskResult(
            "COMPLETED",
            output_uri,
            {"aggregate_report": output_uri},
            {"mvp_demo": result, "input_artifacts": dict(context.artifacts)},
        )
    return _marker(context, {"task": "aggregate_report", "input_artifacts": dict(context.artifacts)})


def _task_config(context: TaskContext, *keys: str) -> dict[str, object]:
    for key in keys:
        value = context.config.get(key)
        if isinstance(value, Mapping):
            return dict(value)
    task_configs = context.config.get("task_configs")
    if isinstance(task_configs, Mapping):
        for key in keys:
            value = task_configs.get(key)
            if isinstance(value, Mapping):
                return dict(value)
    return {}


def _enabled(config: Mapping[str, object], default: bool = False) -> bool:
    value = config.get("enabled", default)
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


def _result_from_payload(context: TaskContext, task_name: str, payload: Mapping[str, object]) -> TaskResult:
    output_uri = _output_uri(payload) or _write_marker(context, task_name, payload)
    return TaskResult("COMPLETED", output_uri, {task_name: output_uri}, dict(payload))


def _marker(context: TaskContext, payload: Mapping[str, object], *, status: str = "COMPLETED") -> TaskResult:
    output_uri = _write_marker(context, context.task_name, payload)
    return TaskResult(status, output_uri, {context.task_name: output_uri}, dict(payload))


def _write_marker(context: TaskContext, task_name: str, payload: Mapping[str, object]) -> str:
    output_path = context.lake_root / "pipeline_runs" / context.run_name / f"{task_name}.json"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(payload, sort_keys=True, indent=2, default=str), encoding="utf-8")
    return output_path.as_posix()


def _output_uri(payload: Mapping[str, object]) -> str:
    for key in ("output_uri", "report_uri", "report_path", "output_path", "path"):
        value = payload.get(key)
        if value:
            return str(value)
    outputs = payload.get("outputs")
    if isinstance(outputs, list) and outputs:
        first = outputs[0]
        if isinstance(first, Mapping):
            for key in ("model_path", "model_card_path", "output_uri"):
                if first.get(key):
                    return str(first[key])
    return ""
