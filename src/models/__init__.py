"""Forecast model abstractions, registries, and inference helpers."""

from __future__ import annotations

from src.models.base import BaseForecastModel, ForecastPrediction
from src.models.registry import build_default_model_registry

__all__ = [
    "BaseForecastModel",
    "ForecastPrediction",
    "build_default_model_registry",
]
