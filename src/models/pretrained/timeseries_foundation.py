"""Base adapter for local-checkpoint pretrained time-series models."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Self

from src.models.base import (
    BaseForecastModel,
    ForecastDataset,
    ForecastPrediction,
    MissingModelCheckpointError,
    load_json_payload,
    numeric_value,
    row_asset_id,
    row_symbol,
    row_timestamp,
    save_json_payload,
)


@dataclass(slots=True)
class TimeseriesFoundationAdapter(BaseForecastModel):
    """Local-checkpoint adapter for pretrained time-series models.

    Example:
        `TimeseriesFoundationAdapter("chronos", checkpoint_path="model.json")`
    """

    model_name: str
    model_version: str = "local"
    checkpoint_path: str | None = None
    cache_dir: str | None = None
    device: str = "cpu"
    batch_size: int = 16
    required_dependency: str = ""
    normalizer_metadata: dict[str, object] = field(default_factory=dict)
    _checkpoint_payload: dict[str, object] = field(default_factory=dict, repr=False)

    @classmethod
    def from_config(cls, config: Mapping[str, object]) -> Self:
        """Build adapter from registry config."""
        return cls(
            model_name=str(config.get("model_name", cls.__name__)),
            model_version=str(config.get("model_version", "local")),
            checkpoint_path=_optional_text(config.get("checkpoint_path")),
            cache_dir=_optional_text(config.get("cache_dir")),
            device=str(config.get("device", "cpu")),
            batch_size=int(config.get("batch_size", 16)),
            normalizer_metadata=dict(config.get("normalizer_metadata", {})),
        )

    def fit(self, dataset: ForecastDataset, config: Mapping[str, object]) -> Self:
        """Pretrained adapters are inference-first; fit records normalization."""
        if config.get("normalizer_metadata"):
            self.normalizer_metadata = dict(config["normalizer_metadata"])
        elif dataset:
            self.normalizer_metadata = _infer_normalizer(dataset)
        return self

    def predict(
        self,
        dataset: ForecastDataset,
        horizon: int | str,
    ) -> list[ForecastPrediction]:
        """Run local checkpoint inference or fail with a clear stub message."""
        payload = self._checkpoint()
        rows: list[ForecastPrediction] = []
        for batch in _batches(dataset, self.batch_size):
            rows.extend(self._predict_batch(batch, horizon, payload))
        return rows

    def explain(
        self,
        dataset: ForecastDataset,
        predictions: Sequence[ForecastPrediction],
    ) -> dict[str, object]:
        """Return adapter explanation metadata."""
        return {
            "model": self.model_name,
            "model_version": self.model_version,
            "device": self.device,
            "batch_size": self.batch_size,
            "checkpoint_path": self.checkpoint_path,
            "normalizer_metadata": dict(self.normalizer_metadata),
            "prediction_count": len(predictions),
        }

    def save(self, path: str | Path) -> Path:
        """Save adapter metadata and local checkpoint payload."""
        return save_json_payload(
            path,
            self.metadata() | {"checkpoint_payload": dict(self._checkpoint_payload)},
        )

    @classmethod
    def load(cls, path: str | Path) -> Self:
        """Load adapter metadata from JSON."""
        payload = load_json_payload(path)
        adapter = cls.from_config(payload)
        adapter._checkpoint_payload = dict(payload.get("checkpoint_payload", {}))
        return adapter

    def metadata(self) -> dict[str, object]:
        """Return registry metadata."""
        return {
            "model_name": self.model_name,
            "model_version": self.model_version,
            "model_type": "pretrained_adapter",
            "checkpoint_path": self.checkpoint_path,
            "cache_dir": self.cache_dir,
            "device": self.device,
            "batch_size": self.batch_size,
            "requires_gpu": False,
            "normalizer_metadata": dict(self.normalizer_metadata),
        }

    def _checkpoint(self) -> dict[str, object]:
        if self._checkpoint_payload:
            return self._checkpoint_payload
        if self.checkpoint_path and Path(self.checkpoint_path).exists():
            self._checkpoint_payload = load_json_payload(self.checkpoint_path)
            return self._checkpoint_payload
        dependency_hint = ""
        if self.required_dependency:
            dependency_hint = (
                " Optional live adapter dependency: "
                f"{self.required_dependency}."
            )
        raise MissingModelCheckpointError(
            f"No local checkpoint for {self.model_name!r}; remote pretrained "
            "downloads are disabled. Provide checkpoint_path or register a local "
            f"model artifact.{dependency_hint}"
        )

    def _predict_batch(
        self,
        dataset: ForecastDataset,
        horizon: int | str,
        payload: Mapping[str, object],
    ) -> list[ForecastPrediction]:
        constant = payload.get("constant_prediction")
        scale = numeric_value(payload.get("last_value_scale", 1.0), 1.0)
        value_column = str(payload.get("value_column", "close"))
        return [
            ForecastPrediction(
                symbol=row_symbol(row),
                ts=row_timestamp(row),
                horizon=str(horizon),
                prediction=_checkpoint_prediction(row, constant, scale, value_column),
                signal=_checkpoint_prediction(row, constant, scale, value_column),
                confidence=numeric_value(payload.get("confidence"), 0.5),
                model_name=self.model_name,
                model_version=self.model_version,
                explanation_json={"adapter": self.model_name, "checkpoint": True},
                asset_id=row_asset_id(row),
            )
            for row in dataset
        ]


def _checkpoint_prediction(
    row: Mapping[str, object],
    constant: object,
    scale: float,
    value_column: str,
) -> float:
    if constant is not None:
        return numeric_value(constant)
    return numeric_value(row.get(value_column)) * scale


def _infer_normalizer(dataset: ForecastDataset) -> dict[str, object]:
    numeric_keys = [
        key
        for key, value in dataset[0].items()
        if key not in {"symbol", "ts", "timestamp", "date"}
        and isinstance(value, int | float)
    ]
    return {"method": "identity", "columns": numeric_keys}


def _batches(dataset: ForecastDataset, batch_size: int) -> list[ForecastDataset]:
    size = max(batch_size, 1)
    return [dataset[index : index + size] for index in range(0, len(dataset), size)]


def _optional_text(value: object) -> str | None:
    if value in (None, ""):
        return None
    return str(value)
