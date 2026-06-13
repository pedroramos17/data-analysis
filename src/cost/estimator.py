"""Dependency-light cost estimates for local and optional GPU workloads."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

from src.config.settings import RuntimeSettings, load_runtime_settings

GPU_MODEL_HINTS = ("mamba", "samba", "tcn", "gru", "attention", "transformer")
BASELINE_MODEL_HINTS = ("baseline", "naive", "ridge", "linear", "mean", "median")
SMALL_DATASET_GB = 2.0
SMOKE_SAMPLE_FRACTION = 0.1
DEFAULT_BASELINE_RUNTIME_SECONDS = 120
DEFAULT_SEQUENCE_RUNTIME_SECONDS = 900
POD_STARTUP_OVERHEAD_SECONDS = 60


@dataclass(frozen=True, slots=True)
class CostOption:
    """One executable cost option for a workload."""

    name: str
    provider: str
    execution_mode: str
    estimated_cost_usd: float
    estimated_runtime_seconds: int
    hourly_cost_usd: float = 0.0
    dataset_size_gb: float = 0.0
    window_count: int = 1
    gpu_required: bool = False
    launches_paid_infrastructure: bool = False
    eligible: bool = True
    reasons: tuple[str, ...] = ()
    actions: tuple[str, ...] = ()
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, object]:
        """Return a JSON-friendly option."""
        return {
            "name": self.name,
            "provider": self.provider,
            "execution_mode": self.execution_mode,
            "estimated_cost_usd": round(self.estimated_cost_usd, 4),
            "estimated_runtime_seconds": self.estimated_runtime_seconds,
            "hourly_cost_usd": round(self.hourly_cost_usd, 4),
            "dataset_size_gb": round(self.dataset_size_gb, 4),
            "window_count": self.window_count,
            "gpu_required": self.gpu_required,
            "launches_paid_infrastructure": self.launches_paid_infrastructure,
            "eligible": self.eligible,
            "reasons": list(self.reasons),
            "actions": list(self.actions),
            "metadata": dict(self.metadata),
        }


@dataclass(frozen=True, slots=True)
class CostEstimate:
    """Cost estimate across local, smoke, and GPU options."""

    workload: dict[str, Any]
    options: tuple[CostOption, ...]
    warnings: tuple[str, ...] = ()

    def cheapest_eligible(self) -> CostOption | None:
        """Return the cheapest eligible option before budget approval checks."""
        candidates = [option for option in self.options if option.eligible]
        if not candidates:
            return None
        return min(candidates, key=lambda option: (option.estimated_cost_usd, option.estimated_runtime_seconds))

    def option(self, name: str) -> CostOption | None:
        """Return an option by name."""
        for option in self.options:
            if option.name == name:
                return option
        return None

    def to_dict(self) -> dict[str, object]:
        """Return a JSON-friendly estimate."""
        cheapest = self.cheapest_eligible()
        return {
            "workload": dict(self.workload),
            "recommended_option": cheapest.name if cheapest else None,
            "options": [option.to_dict() for option in self.options],
            "warnings": list(self.warnings),
        }


def estimate_costs(
    config: Mapping[str, object],
    settings: RuntimeSettings | None = None,
) -> CostEstimate:
    """Estimate local, smoke, RunPod, and batched RunPod costs."""
    active_settings = settings or load_runtime_settings()
    workload = _workload(config, active_settings)
    options = (
        _local_cpu_option(workload),
        _local_smoke_option(workload),
        _runpod_option(workload, active_settings, batched=False),
        _runpod_option(workload, active_settings, batched=True),
    )
    warnings = _warnings(workload, options)
    return CostEstimate(workload=workload, options=options, warnings=warnings)


def _workload(config: Mapping[str, object], settings: RuntimeSettings) -> dict[str, Any]:
    model_name = str(config.get("model_name") or config.get("model_type") or "naive_return")
    dataset_size_gb = _float(config.get("dataset_size_gb") or _nested(config, "cost_estimate", "dataset_size_gb"), 0.0)
    window_count = _window_count(config)
    selected_window_count = _selected_window_count(config)
    effective_window_count = selected_window_count or window_count
    smoke_mode = _bool(config.get("smoke_mode") or config.get("smoke") or config.get("downsample_smoke"), False)
    sample_fraction = _sample_fraction(config, smoke_mode)
    device = str(config.get("device") or settings.pipeline.model_device).lower()
    force_gpu = _bool(config.get("force_gpu") or config.get("gpu_required") or config.get("requires_gpu"), False)
    gpu_required = force_gpu or device == "cuda"
    prefers_gpu = _model_prefers_gpu(model_name)
    baseline_model = _model_is_baseline(model_name)
    full_training_requested = _bool(
        config.get("full_training")
        or config.get("force_full_training")
        or config.get("generate_runpod_spec")
        or gpu_required,
        False,
    )
    base_runtime_seconds = _base_runtime_seconds(config, model_name, dataset_size_gb, effective_window_count)
    per_window_runtime_seconds = max(base_runtime_seconds // max(effective_window_count, 1), 30)
    optimized_runtime_seconds, runtime_reasons = _optimized_runtime(base_runtime_seconds, config)
    remote_uris = _remote_uris(config)
    return {
        "model_name": model_name,
        "training_mode": str(config.get("training_mode") or "single"),
        "baseline_model": baseline_model,
        "prefers_gpu": prefers_gpu,
        "gpu_required": gpu_required,
        "force_gpu": force_gpu,
        "full_training_requested": full_training_requested,
        "dataset_size_gb": dataset_size_gb,
        "is_small_dataset": dataset_size_gb <= SMALL_DATASET_GB,
        "window_count": max(window_count, 1),
        "selected_window_count": selected_window_count,
        "effective_window_count": max(effective_window_count, 1),
        "smoke_mode": smoke_mode,
        "sample_fraction": sample_fraction,
        "base_runtime_seconds": base_runtime_seconds,
        "optimized_runtime_seconds": optimized_runtime_seconds,
        "per_window_runtime_seconds": per_window_runtime_seconds,
        "runtime_reduction_reasons": runtime_reasons,
        "hourly_cost_usd": _float(
            config.get("hourly_cost_usd") or config.get("runpod_hourly_cost_usd"),
            settings.runpod.max_hourly_cost_usd,
        ),
        "max_runtime_seconds": _int(
            config.get("max_runtime_seconds") or config.get("runpod_max_runtime_seconds"),
            settings.runpod.max_runtime_seconds,
        ),
        "min_gpu_memory_gb": _int(
            config.get("min_gpu_memory_gb") or config.get("runpod_min_gpu_memory_gb"),
            settings.runpod.min_gpu_memory_gb,
        ),
        "remote_uris": remote_uris,
        "uses_remote_artifacts": bool(remote_uris),
        "reuse_cached_features": _bool(
            config.get("reuse_cached_features") or config.get("features_cached") or config.get("cached_features"),
            False,
        ),
        "reuse_pretrained_model": _bool(
            config.get("reuse_pretrained_model") or config.get("pretrained_model_uri") or config.get("pretrained_model_path"),
            False,
        ),
        "docker_image_cached": _bool(config.get("docker_image_cached") or config.get("image_cached"), False),
        "prefer_spot": _bool(config.get("prefer_spot"), settings.autoscaling.prefer_spot)
        and settings.runpod.enable_spot,
        "batch_small_jobs": settings.autoscaling.batch_small_jobs,
        "cost_mode": settings.pipeline.cost_mode,
    }


def _local_cpu_option(workload: Mapping[str, Any]) -> CostOption:
    eligible = not bool(workload["gpu_required"])
    reasons = [] if eligible else ["GPU was explicitly requested"]
    if workload["baseline_model"]:
        reasons.append("baseline model is CPU-friendly")
    elif workload["is_small_dataset"] and not workload["gpu_required"]:
        reasons.append("small dataset stays local unless GPU is forced")
    actions = ["run_local_cpu"]
    if workload["reuse_cached_features"]:
        actions.append("reuse_cached_features")
    if workload["selected_window_count"]:
        actions.append("select_training_windows")
    return CostOption(
        name="local_cpu",
        provider="local",
        execution_mode="cpu_full",
        estimated_cost_usd=0.0,
        estimated_runtime_seconds=int(workload["optimized_runtime_seconds"]),
        dataset_size_gb=float(workload["dataset_size_gb"]),
        window_count=int(workload["effective_window_count"]),
        gpu_required=False,
        launches_paid_infrastructure=False,
        eligible=eligible,
        reasons=tuple(reasons),
        actions=tuple(actions),
        metadata={
            "runtime_reduction_reasons": list(workload["runtime_reduction_reasons"]),
        },
    )


def _local_smoke_option(workload: Mapping[str, Any]) -> CostOption:
    sample_fraction = float(workload["sample_fraction"])
    if sample_fraction >= 1.0:
        sample_fraction = SMOKE_SAMPLE_FRACTION
    smoke_windows = 1 if int(workload["effective_window_count"]) > 1 else int(workload["effective_window_count"])
    runtime = max(int(int(workload["optimized_runtime_seconds"]) * sample_fraction), 30)
    return CostOption(
        name="local_smoke",
        provider="local",
        execution_mode="cpu_smoke",
        estimated_cost_usd=0.0,
        estimated_runtime_seconds=runtime,
        dataset_size_gb=round(float(workload["dataset_size_gb"]) * sample_fraction, 4),
        window_count=smoke_windows,
        gpu_required=False,
        launches_paid_infrastructure=False,
        eligible=True,
        reasons=("smoke mode samples data and windows before paid training",),
        actions=("run_local_smoke", "downsample_smoke", "select_training_windows"),
        metadata={
            "sample_fraction": sample_fraction,
            "original_window_count": int(workload["effective_window_count"]),
        },
    )


def _runpod_option(
    workload: Mapping[str, Any],
    settings: RuntimeSettings,
    *,
    batched: bool,
) -> CostOption:
    if batched:
        runtime = _batched_gpu_runtime_seconds(workload)
        name = "runpod_batched_gpu"
        mode = "gpu_batched_windows"
        actions = ["submit_runpod_batched_gpu"]
    else:
        runtime = _single_gpu_runtime_seconds(workload)
        name = "runpod_gpu"
        mode = "gpu_full"
        actions = ["submit_runpod_gpu"]
    hourly_cost = max(float(workload["hourly_cost_usd"]), 0.0)
    estimated_cost = runtime * hourly_cost / 3600.0
    considers_gpu = bool(workload["gpu_required"] or workload["prefers_gpu"])
    eligible = considers_gpu and (not batched or int(workload["effective_window_count"]) > 1)
    reasons: list[str] = []
    if not considers_gpu:
        reasons.append("workload does not need GPU")
    if batched and int(workload["effective_window_count"]) <= 1:
        reasons.append("batching needs multiple windows")
    if batched and not bool(workload["batch_small_jobs"]):
        eligible = False
        reasons.append("autoscaling batch_small_jobs is disabled")
    if bool(workload["prefer_spot"]):
        actions.append("prefer_spot_capacity")
        reasons.append("spot capacity preferred when available")
    if bool(workload["reuse_cached_features"]):
        actions.append("reuse_cached_features")
    if bool(workload["reuse_pretrained_model"]):
        actions.append("reuse_pretrained_model")
    if bool(workload["docker_image_cached"]):
        actions.append("reuse_docker_image_cache")
    return CostOption(
        name=name,
        provider="runpod",
        execution_mode=mode,
        estimated_cost_usd=estimated_cost,
        estimated_runtime_seconds=runtime,
        hourly_cost_usd=hourly_cost,
        dataset_size_gb=float(workload["dataset_size_gb"]),
        window_count=int(workload["effective_window_count"]),
        gpu_required=bool(workload["gpu_required"]),
        launches_paid_infrastructure=not settings.runpod.dry_run,
        eligible=eligible,
        reasons=tuple(reasons),
        actions=tuple(actions),
        metadata={
            "dry_run": settings.runpod.dry_run,
            "gpu_type": settings.runpod.gpu_type,
            "min_gpu_memory_gb": int(workload["min_gpu_memory_gb"]),
            "max_runtime_seconds": int(workload["max_runtime_seconds"]),
            "runtime_reduction_reasons": list(workload["runtime_reduction_reasons"]),
            "uses_remote_artifacts": bool(workload["uses_remote_artifacts"]),
            "remote_uris": list(workload["remote_uris"]),
            "prefer_spot": bool(workload["prefer_spot"]),
            "spot_discount_applied": False,
        },
    )


def _single_gpu_runtime_seconds(workload: Mapping[str, Any]) -> int:
    windows = max(int(workload["effective_window_count"]), 1)
    runtime = min(
        int(workload["optimized_runtime_seconds"]) + POD_STARTUP_OVERHEAD_SECONDS * windows,
        int(workload["max_runtime_seconds"]),
    )
    return max(runtime, 60)


def _batched_gpu_runtime_seconds(workload: Mapping[str, Any]) -> int:
    windows = max(int(workload["effective_window_count"]), 1)
    per_window = max(int(workload["per_window_runtime_seconds"]), 30)
    runtime = per_window * windows + POD_STARTUP_OVERHEAD_SECONDS
    if bool(workload["docker_image_cached"]):
        runtime = max(runtime - POD_STARTUP_OVERHEAD_SECONDS // 2, 60)
    return min(runtime, int(workload["max_runtime_seconds"]))


def _warnings(workload: Mapping[str, Any], options: tuple[CostOption, ...]) -> tuple[str, ...]:
    warnings: list[str] = []
    if workload["gpu_required"] and workload["is_small_dataset"]:
        warnings.append("GPU is forced for a small dataset; local smoke or CPU may be cheaper")
    if workload["prefers_gpu"] and not workload["full_training_requested"]:
        warnings.append("GPU-preferring model should use smoke/local planning until full training is explicit")
    if not any(option.eligible for option in options):
        warnings.append("no eligible execution option found before budget checks")
    return tuple(warnings)


def _base_runtime_seconds(
    config: Mapping[str, object],
    model_name: str,
    dataset_size_gb: float,
    window_count: int,
) -> int:
    configured = _int(config.get("estimated_runtime_seconds") or config.get("runtime_seconds"), 0)
    if configured > 0:
        return configured
    max_runtime = _int(config.get("max_runtime_seconds"), 0)
    if max_runtime > 0:
        return max_runtime
    base = DEFAULT_SEQUENCE_RUNTIME_SECONDS if _model_prefers_gpu(model_name) else DEFAULT_BASELINE_RUNTIME_SECONDS
    dataset_factor = max(dataset_size_gb, 0.25)
    epochs_factor = max(_int(config.get("epochs"), 1), 1)
    return int(base * dataset_factor * max(window_count, 1) * min(epochs_factor, 10) ** 0.5)


def _optimized_runtime(runtime_seconds: int, config: Mapping[str, object]) -> tuple[int, tuple[str, ...]]:
    runtime = float(max(runtime_seconds, 30))
    reasons: list[str] = []
    if _bool(config.get("reuse_cached_features") or config.get("features_cached") or config.get("cached_features"), False):
        runtime *= 0.7
        reasons.append("cached_features")
    if _bool(config.get("reuse_pretrained_model") or config.get("pretrained_model_uri") or config.get("pretrained_model_path"), False):
        runtime *= 0.8
        reasons.append("pretrained_model")
    if _bool(config.get("docker_image_cached") or config.get("image_cached"), False):
        runtime = max(runtime - POD_STARTUP_OVERHEAD_SECONDS, 30)
        reasons.append("docker_image_cache")
    return max(int(runtime), 30), tuple(reasons)


def _window_count(config: Mapping[str, object]) -> int:
    for key in ("window_count", "num_windows", "training_windows"):
        value = _int(config.get(key), 0)
        if value > 0:
            return value
    windows = config.get("windows")
    if isinstance(windows, Sequence) and not isinstance(windows, (str, bytes)):
        return max(len(windows), 1)
    return 1


def _selected_window_count(config: Mapping[str, object]) -> int:
    selected = config.get("selected_windows") or config.get("window_ids")
    if isinstance(selected, Sequence) and not isinstance(selected, (str, bytes)):
        return len(selected)
    if isinstance(selected, str) and selected.strip():
        return len([item for item in selected.split(",") if item.strip()])
    window_id = config.get("window_id")
    if window_id not in (None, ""):
        return 1
    return 0


def _sample_fraction(config: Mapping[str, object], smoke_mode: bool) -> float:
    value = _float(config.get("sample_fraction") or config.get("smoke_sample_fraction"), 0.0)
    if value > 0:
        return min(value, 1.0)
    return SMOKE_SAMPLE_FRACTION if smoke_mode else 1.0


def _remote_uris(config: Mapping[str, object]) -> tuple[str, ...]:
    keys = ("dataset_uri", "output_uri", "logs_uri", "metrics_uri", "artifact_uri")
    uris = [str(config.get(key) or "") for key in keys]
    return tuple(uri for uri in uris if _is_remote_uri(uri))


def _nested(config: Mapping[str, object], section: str, key: str) -> object:
    payload = config.get(section)
    if isinstance(payload, Mapping):
        return payload.get(key)
    return None


def _model_prefers_gpu(model_name: str) -> bool:
    normalized = model_name.lower()
    return any(hint in normalized for hint in GPU_MODEL_HINTS)


def _model_is_baseline(model_name: str) -> bool:
    normalized = model_name.lower()
    return any(hint in normalized for hint in BASELINE_MODEL_HINTS)


def _is_remote_uri(value: str) -> bool:
    return value.startswith(("s3://", "r2://", "b2://", "minio://", "gs://"))


def _bool(value: object, default: bool) -> bool:
    if value in (None, ""):
        return default
    if isinstance(value, bool):
        return value
    normalized = str(value).strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off", "none", "null"}:
        return False
    return True


def _float(value: object, default: float) -> float:
    if value in (None, ""):
        return default
    return float(value)


def _int(value: object, default: int) -> int:
    if value in (None, ""):
        return default
    return int(value)
