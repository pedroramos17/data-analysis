"""Lazy PyTorch helpers for optional sequence modules."""

from __future__ import annotations

from src.models.base import MissingModelDependencyError


def torch_modules(feature_name: str) -> tuple[object, object]:
    """Return torch and torch.nn or raise a clear optional dependency error."""
    try:
        import torch
        import torch.nn as nn
    except ImportError as exc:
        raise MissingModelDependencyError(
            f"torch is required for {feature_name}; expected optional PyTorch "
            "dependency. CPU inference is supported when torch is installed."
        ) from exc
    return torch, nn
