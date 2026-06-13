"""RunPod and local job spec builders for training workloads."""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from src.cli_commands import src_cli_command


@dataclass(frozen=True, slots=True)
class TrainingJobSpec:
    """Provider-neutral training job specification."""

    name: str
    model_name: str
    dataset_uri: str
    config_path: str
    output_uri: str
    command: str
    provider: str = "local"
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, object]:
        return {
            "name": self.name,
            "model_name": self.model_name,
            "dataset_uri": self.dataset_uri,
            "config_path": self.config_path,
            "output_uri": self.output_uri,
            "command": self.command,
            "provider": self.provider,
            "metadata": dict(self.metadata),
        }

    def to_runpod_payload(self) -> dict[str, object]:
        """Convert to a RunPod-compatible job payload."""
        return {
            "name": self.name,
            "task": f"train_{self.model_name}",
            "command": self.command,
            "payload": {
                "model_name": self.model_name,
                "dataset_uri": self.dataset_uri,
                "config_path": self.config_path,
                "output_uri": self.output_uri,
            },
        }


def build_training_job_spec(
    config: Mapping[str, object],
    provider: str = "local",
) -> TrainingJobSpec:
    """Build a training job spec from config."""
    model_name = str(config.get("model_name") or "naive_return")
    dataset_uri = str(
        config.get("dataset_uri")
        or config.get("dataset_path")
        or "data/lake/datasets/dataset=default/window_id=0"
    )
    config_path = str(config.get("config_path") or "")
    output_uri = str(
        config.get("output_uri") or config.get("output_path") or f"models/{model_name}"
    )
    name = str(config.get("job_name") or f"train_{model_name}")
    command = str(
        config.get("command")
        or src_cli_command(
            "train",
            "run",
            "--config",
            config_path or "configs/train.yaml",
        )
    )
    return TrainingJobSpec(
        name=name,
        model_name=model_name,
        dataset_uri=dataset_uri,
        config_path=config_path,
        output_uri=output_uri,
        command=command,
        provider=provider,
        metadata=dict(config.get("job_metadata", {})),
    )


def write_job_spec(
    spec: TrainingJobSpec,
    path: str | Path,
) -> Path:
    """Write a job spec JSON to disk."""
    output = Path(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(spec.to_dict(), sort_keys=True, indent=2), encoding="utf-8")
    return output
