"""Checkpointing helpers for model state persistence."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from src.storage.manifest import content_hash


@dataclass(frozen=True, slots=True)
class CheckpointRecord:
    """Metadata for a saved checkpoint."""

    epoch: int
    path: str
    metric_value: float
    metric_name: str
    content_hash: str
    created_at: str

    def to_dict(self) -> dict[str, object]:
        return {
            "epoch": self.epoch,
            "path": self.path,
            "metric_value": self.metric_value,
            "metric_name": self.metric_name,
            "content_hash": self.content_hash,
            "created_at": self.created_at,
        }


def save_checkpoint(
    model: object,
    path: str | Path,
    epoch: int,
    metric_value: float,
    metric_name: str = "val_loss",
) -> CheckpointRecord:
    """Save a model checkpoint and return metadata.

    If the model has a `save_checkpoint` method (PyTorch), use it.
    Otherwise fall back to JSON metadata.
    """
    checkpoint_path = Path(path)
    checkpoint_path.parent.mkdir(parents=True, exist_ok=True)

    if hasattr(model, "save_checkpoint"):
        model.save_checkpoint(checkpoint_path)
    elif hasattr(model, "save"):
        model.save(checkpoint_path)
    else:
        metadata = {
            "epoch": epoch,
            "metric_value": metric_value,
            "metric_name": metric_name,
            "model_type": type(model).__name__,
        }
        checkpoint_path.write_text(json.dumps(metadata, sort_keys=True, indent=2), encoding="utf-8")

    data = checkpoint_path.read_bytes()
    return CheckpointRecord(
        epoch=epoch,
        path=str(checkpoint_path),
        metric_value=metric_value,
        metric_name=metric_name,
        content_hash=content_hash(data),
        created_at=datetime.now(UTC).isoformat(),
    )


def load_checkpoint(model: object, path: str | Path) -> dict[str, Any]:
    """Load a checkpoint into a model.

    If the model has a `load_checkpoint` method, use it.
    Otherwise return empty metadata.
    """
    checkpoint_path = Path(path)
    if hasattr(model, "load_checkpoint"):
        model.load_checkpoint(checkpoint_path)
        return {"loaded_from": str(checkpoint_path), "method": "load_checkpoint"}
    if hasattr(model, "load"):
        loaded = model.load(checkpoint_path)
        return {"loaded_from": str(checkpoint_path), "method": "load", "result": str(loaded)}
    return {"loaded_from": str(checkpoint_path), "method": "none"}


def clean_old_checkpoints(
    checkpoint_dir: Path,
    keep: int = 3,
) -> list[str]:
    """Remove old checkpoints, keeping the N most recent by filename sort."""
    if not checkpoint_dir.exists():
        return []
    checkpoints = sorted(checkpoint_dir.glob("*.pt*"), reverse=True)
    removed: list[str] = []
    for path in checkpoints[keep:]:
        path.unlink()
        removed.append(str(path))
    return removed
