"""Phase 7 training pipeline runner."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from src.config.settings import load_runtime_settings
from src.pipeline.features.base import read_feature_input_rows
from src.pipeline.training.job_spec import build_training_job_spec, write_job_spec
from src.pipeline.training.runpod_job import submit_runpod_training_job as _submit_runpod_job
from src.pipeline.training.trainer import TrainResult, train_model
from src.providers.registry import ProviderRegistry, build_provider_registry


@dataclass(frozen=True, slots=True)
class TrainingPipelineResult:
    """Top-level training pipeline result."""

    status: str
    model_name: str
    outputs: list[TrainResult]
    runpod_spec_path: str | None
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, object]:
        return {
            "status": self.status,
            "model_name": self.model_name,
            "outputs": [o.to_dict() for o in self.outputs],
            "runpod_spec_path": self.runpod_spec_path,
            "metadata": dict(self.metadata),
        }


def run_training(
    config: Mapping[str, object],
    registry: ProviderRegistry | None = None,
) -> TrainingPipelineResult:
    """Run training from config: local training + optional RunPod spec generation."""
    active_registry = registry or build_provider_registry(load_runtime_settings())
    model_name = str(config.get("model_name") or "naive_return")
    mode = str(config.get("training_mode") or "single")
    output_root = _config_path(config, "output_root", active_registry.settings.storage.local_root / "models")
    dataset_path = _config_path(config, "dataset_path", active_registry.settings.storage.local_root / "datasets")

    outputs: list[TrainResult] = []
    runpod_spec_path: str | None = None

    if mode == "windowed":
        outputs = _run_windowed_training(config, active_registry, model_name, output_root, dataset_path)
    else:
        result = _run_single_training(config, active_registry, model_name, output_root, dataset_path)
        outputs.append(result)

    # Generate RunPod spec if requested
    if bool(config.get("generate_runpod_spec", False)):
        spec = build_training_job_spec(config, provider="runpod")
        spec_path = output_root / model_name / "runpod_job_spec.json"
        write_job_spec(spec, spec_path)
        runpod_spec_path = str(spec_path)

    return TrainingPipelineResult(
        status="COMPLETED",
        model_name=model_name,
        outputs=outputs,
        runpod_spec_path=runpod_spec_path,
        metadata={
            "mode": mode,
            "output_root": str(output_root),
            "dataset_path": str(dataset_path),
        },
    )


def _run_single_training(
    config: Mapping[str, object],
    registry: ProviderRegistry,
    model_name: str,
    output_root: Path,
    dataset_path: Path,
) -> TrainResult:
    """Train on a single train/validation split."""
    train_uri = str(config.get("train_uri") or config.get("train_path") or str(dataset_path / "train.parquet"))
    val_uri = str(config.get("validation_uri") or config.get("validation_path") or str(dataset_path / "validation.parquet"))

    train_rows, _, _ = read_feature_input_rows(train_uri, require_duckdb=_bool(config.get("require_duckdb"), False))
    val_rows, _, _ = read_feature_input_rows(val_uri, require_duckdb=_bool(config.get("require_duckdb"), False))

    output_dir = output_root / model_name
    output_dir.mkdir(parents=True, exist_ok=True)

    return train_model(
        model_name=model_name,
        train_rows=train_rows,
        val_rows=val_rows,
        config=config,
        output_dir=output_dir,
    )


def _run_windowed_training(
    config: Mapping[str, object],
    registry: ProviderRegistry,
    model_name: str,
    output_root: Path,
    dataset_path: Path,
) -> list[TrainResult]:
    """Train on each sliding window independently."""
    dataset_name = str(config.get("dataset_name") or "default_dataset")
    version = str(config.get("version") or "phase6_v1")
    base_path = dataset_path / f"dataset={dataset_name}" / f"version={version}"

    results: list[TrainResult] = []
    if not base_path.exists():
        return results

    for window_dir in sorted(base_path.iterdir()):
        if not window_dir.is_dir() or not window_dir.name.startswith("window_id="):
            continue
        window_id = window_dir.name.split("=", 1)[1]
        train_path = window_dir / "train.parquet"
        val_path = window_dir / "validation.parquet"
        if not train_path.exists() or not val_path.exists():
            continue

        train_rows, _, _ = read_feature_input_rows(train_path, require_duckdb=_bool(config.get("require_duckdb"), False))
        val_rows, _, _ = read_feature_input_rows(val_path, require_duckdb=_bool(config.get("require_duckdb"), False))

        output_dir = output_root / model_name / f"window_{window_id}"
        output_dir.mkdir(parents=True, exist_ok=True)

        result = train_model(
            model_name=model_name,
            train_rows=train_rows,
            val_rows=val_rows,
            config=config,
            output_dir=output_dir,
        )
        results.append(result)

    return results


def submit_runpod_training_job(
    config: Mapping[str, object],
    registry: ProviderRegistry,
    *,
    confirm_cost: bool = False,
    dry_run: bool = False,
) -> dict[str, object]:
    """Submit a training job to RunPod (dry-run by default)."""
    return _submit_runpod_job(config, registry, confirm_cost=confirm_cost, dry_run=dry_run)


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
