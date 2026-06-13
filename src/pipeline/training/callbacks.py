"""Training callbacks: early stopping, gradient clipping, LR scheduling."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any


@dataclass
class EarlyStopping:
    """Early stopping with patience and optional delta."""

    patience: int = 10
    min_delta: float = 1e-4
    mode: str = "min"
    counter: int = field(default=0, init=False)
    best_value: float | None = field(default=None, init=False)
    stopped_epoch: int | None = field(default=None, init=False)

    def __call__(self, epoch: int, metric_value: float) -> bool:
        """Return True if training should stop."""
        if self.best_value is None:
            self.best_value = metric_value
            return False

        improved = False
        if self.mode == "min":
            improved = metric_value < self.best_value - self.min_delta
        else:
            improved = metric_value > self.best_value + self.min_delta

        if improved:
            self.best_value = metric_value
            self.counter = 0
        else:
            self.counter += 1

        if self.counter >= self.patience:
            self.stopped_epoch = epoch
            return True
        return False

    def to_dict(self) -> dict[str, Any]:
        return {
            "patience": self.patience,
            "min_delta": self.min_delta,
            "mode": self.mode,
            "counter": self.counter,
            "best_value": self.best_value,
            "stopped_epoch": self.stopped_epoch,
        }


@dataclass
class GradientClipper:
    """Gradient clipping configuration."""

    max_norm: float = 1.0
    enabled: bool = True

    def apply(self, model: object) -> None:
        """Apply gradient clipping if torch is available."""
        if not self.enabled:
            return
        try:
            import torch
            if hasattr(model, "parameters"):
                torch.nn.utils.clip_grad_norm_(model.parameters(), self.max_norm)
        except ImportError:
            pass

    def to_dict(self) -> dict[str, Any]:
        return {"max_norm": self.max_norm, "enabled": self.enabled}


@dataclass
class LRScheduler:
    """Simple learning rate scheduler (step decay)."""

    initial_lr: float = 1e-3
    decay_factor: float = 0.5
    decay_epochs: int = 10
    min_lr: float = 1e-6

    def get_lr(self, epoch: int) -> float:
        """Return the learning rate for the given epoch."""
        lr = self.initial_lr * (self.decay_factor ** (epoch // self.decay_epochs))
        return max(lr, self.min_lr)

    def to_dict(self) -> dict[str, Any]:
        return {
            "initial_lr": self.initial_lr,
            "decay_factor": self.decay_factor,
            "decay_epochs": self.decay_epochs,
            "min_lr": self.min_lr,
        }


@dataclass
class MetricLogger:
    """Simple in-memory metric logger."""

    history: list[dict[str, Any]] = field(default_factory=list)

    def log(self, epoch: int, metrics: Mapping[str, Any], phase: str = "train") -> None:
        entry = {"epoch": epoch, "phase": phase}
        entry.update(metrics)
        self.history.append(entry)

    def to_dict(self) -> dict[str, Any]:
        return {"history": [dict(h) for h in self.history]}

    def best_epoch(self, metric: str = "val_loss", mode: str = "min") -> dict[str, Any] | None:
        if not self.history:
            return None
        entries = [h for h in self.history if metric in h]
        if not entries:
            return None
        if mode == "min":
            return min(entries, key=lambda x: float(x[metric]))
        return max(entries, key=lambda x: float(x[metric]))
