"""Stable forecast model interface for baselines and pretrained adapters."""

from __future__ import annotations

import json
from abc import ABC, abstractmethod
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Self

ForecastDataset = Sequence[Mapping[str, object]]


class ModelLayerError(RuntimeError):
    """Base model-layer failure with actionable context."""


class MissingModelDependencyError(ModelLayerError):
    """Raised when an optional model dependency is not installed."""


class MissingModelCheckpointError(ModelLayerError):
    """Raised when a pretrained adapter has no local checkpoint."""


@dataclass(frozen=True, slots=True)
class ForecastPrediction:
    """Provider-neutral forecast prediction row.

    Example:
        `ForecastPrediction("SPY", "2024-01-01", "1d", 0.01, 0.01)`
    """

    symbol: str
    ts: str
    horizon: str
    prediction: float
    signal: float
    confidence: float | None = None
    model_name: str = ""
    model_version: str = ""
    explanation_json: Mapping[str, object] = field(default_factory=dict)
    asset_id: int | None = None

    def to_dict(self) -> dict[str, object]:
        """Return a JSON/Parquet-friendly row."""
        return {
            "symbol": self.symbol,
            "ts": self.ts,
            "horizon": self.horizon,
            "prediction": self.prediction,
            "signal": self.signal,
            "confidence": self.confidence,
            "model_name": self.model_name,
            "model_version": self.model_version,
            "explanation_json": dict(self.explanation_json),
            "asset_id": self.asset_id,
        }


class BaseForecastModel(ABC):
    """Stable interface implemented by all forecast models.

    Example:
        `model.fit(dataset, {}).predict(dataset, "1d")`
    """

    @abstractmethod
    def fit(
        self,
        dataset: ForecastDataset,
        config: Mapping[str, object],
    ) -> Self:
        """Fit model state from a training dataset."""

    @abstractmethod
    def predict(
        self,
        dataset: ForecastDataset,
        horizon: int | str,
    ) -> list[ForecastPrediction]:
        """Return forecast predictions for the dataset."""

    @abstractmethod
    def explain(
        self,
        dataset: ForecastDataset,
        predictions: Sequence[ForecastPrediction],
    ) -> dict[str, object]:
        """Return model- and prediction-level explanation metadata."""

    @abstractmethod
    def save(self, path: str | Path) -> Path:
        """Save model state to a local path."""

    @classmethod
    @abstractmethod
    def load(cls, path: str | Path) -> Self:
        """Load model state from a local path."""

    @abstractmethod
    def metadata(self) -> dict[str, object]:
        """Return model metadata for registries and manifests."""


def save_json_payload(path: str | Path, payload: Mapping[str, object]) -> Path:
    """Write a deterministic JSON model payload."""
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(payload, sort_keys=True, indent=2, default=str),
        encoding="utf-8",
    )
    return output_path


def load_json_payload(path: str | Path) -> dict[str, Any]:
    """Read a JSON model payload."""
    loaded = json.loads(Path(path).read_text(encoding="utf-8"))
    if isinstance(loaded, dict):
        return loaded
    raise ValueError(f"Invalid model payload {path!s}; expected JSON object")


def require_optional_module(module_name: str, feature_name: str) -> object:
    """Import an optional dependency or raise a clear model-layer error."""
    try:
        return __import__(module_name)
    except ImportError as exc:
        raise MissingModelDependencyError(
            f"{module_name} is required for {feature_name}; expected installed "
            "optional dependency or local checkpoint"
        ) from exc


def row_symbol(row: Mapping[str, object]) -> str:
    """Return a prediction row symbol."""
    return str(row.get("symbol") or row.get("asset_symbol") or "UNKNOWN")


def row_timestamp(row: Mapping[str, object]) -> str:
    """Return a prediction row timestamp as text."""
    return str(row.get("ts") or row.get("timestamp") or row.get("date") or "")


def row_asset_id(row: Mapping[str, object]) -> int | None:
    """Return an optional asset id for SQL signal persistence."""
    value = row.get("asset_id")
    if value in (None, ""):
        return None
    return int(value)


def numeric_value(value: object, default: float = 0.0) -> float:
    """Parse a finite numeric value for baseline models."""
    try:
        return float(value)
    except (TypeError, ValueError):
        return default
