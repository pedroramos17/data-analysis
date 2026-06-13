"""RunPod training job helpers kept behind provider facades."""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any

from src.cli_commands import src_cli_command
from src.pipeline.training.job_spec import build_training_job_spec
from src.providers.registry import ProviderRegistry


def build_runpod_training_payload(
    config: Mapping[str, object],
    registry: ProviderRegistry,
    *,
    confirm_cost: bool = False,
    dry_run: bool = False,
) -> dict[str, object]:
    """Build a provider-neutral RunPod training payload from config."""
    spec = build_training_job_spec(config, provider="runpod")
    payload = spec.to_runpod_payload()
    runpod_payload = payload.setdefault("payload", {})
    if not isinstance(runpod_payload, dict):
        runpod_payload = {}
        payload["payload"] = runpod_payload

    config_path = str(config.get("config_path") or config.get("config") or "configs/train_gpu.yaml")
    command = str(config.get("command") or src_cli_command("train", "run-windowed", "--config", config_path))
    output_uri = str(config.get("output_uri") or config.get("artifact_uri") or _default_output_uri(config))
    runpod_payload.update(
        {
            "model_name": spec.model_name,
            "dataset_uri": spec.dataset_uri,
            "config_path": config_path,
            "output_uri": output_uri,
            "logs_uri": str(config.get("logs_uri") or _child_uri(output_uri, "logs")),
            "metrics_uri": str(config.get("metrics_uri") or _child_uri(output_uri, "metrics")),
            "confirm_cost": confirm_cost,
        }
    )
    payload.update(
        {
            "command": command,
            "dry_run": dry_run,
            "confirm_cost": confirm_cost,
            "max_runtime_seconds": _int_config(
                config,
                ("max_runtime_seconds", "runpod_max_runtime_seconds"),
                registry.settings.runpod.max_runtime_seconds,
            ),
            "idle_timeout_seconds": _int_config(
                config,
                ("idle_timeout_seconds", "runpod_idle_timeout_seconds"),
                registry.settings.runpod.idle_timeout_seconds,
            ),
            "dataset_size_gb": _float_config(config, ("dataset_size_gb",), 0.0),
            "hourly_cost_usd": _float_config(
                config,
                ("hourly_cost_usd", "runpod_hourly_cost_usd"),
                registry.settings.runpod.max_hourly_cost_usd,
            ),
            "min_gpu_memory_gb": _int_config(
                config,
                ("min_gpu_memory_gb", "runpod_min_gpu_memory_gb"),
                registry.settings.runpod.min_gpu_memory_gb,
            ),
            "model_device": str(config.get("device") or registry.settings.pipeline.model_device),
            "image": str(config.get("image") or config.get("runpod_image") or registry.settings.runpod.image),
            "gpu_type": str(config.get("gpu_type") or config.get("runpod_gpu_type") or registry.settings.runpod.gpu_type),
        }
    )
    if bool(config.get("public_jupyter_enabled", False)):
        payload["public_jupyter_enabled"] = True
    if bool(config.get("ssh_enabled", False)):
        payload["ssh_enabled"] = True
    return payload


def submit_runpod_training_job(
    config: Mapping[str, object],
    registry: ProviderRegistry,
    *,
    confirm_cost: bool = False,
    dry_run: bool = False,
) -> dict[str, object]:
    """Submit a RunPod training job through the configured compute provider."""
    submission = registry.get_compute().submit_job(
        build_runpod_training_payload(
            config,
            registry,
            confirm_cost=confirm_cost,
            dry_run=dry_run,
        )
    )
    return {
        "job_id": submission.job_id,
        "status": submission.status,
        "metadata": submission.metadata,
    }


def _default_output_uri(config: Mapping[str, object]) -> str:
    model_name = str(config.get("model_name") or "model")
    return str(Path("models") / model_name)


def _child_uri(uri: str, child: str) -> str:
    if not uri:
        return ""
    return uri.rstrip("/") + "/" + child


def _int_config(config: Mapping[str, object], keys: tuple[str, ...], default: int) -> int:
    value = _first_config(config, keys)
    if value in (None, ""):
        return default
    return int(value)


def _float_config(config: Mapping[str, object], keys: tuple[str, ...], default: float) -> float:
    value = _first_config(config, keys)
    if value in (None, ""):
        return default
    return float(value)


def _first_config(config: Mapping[str, object], keys: tuple[str, ...]) -> Any:
    for key in keys:
        if key in config:
            return config[key]
    return None
