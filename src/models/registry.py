"""Model registry for baseline, pretrained, and sequence forecast models."""

from __future__ import annotations

import json
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from src.models.base import BaseForecastModel
from src.models.baselines import (
    NaiveReturnBaseline,
    OptionalBoostedBaseline,
    RidgeReturnBaseline,
)

ModelFactory = Callable[[Mapping[str, object]], BaseForecastModel]


@dataclass(slots=True)
class ForecastModelRegistry:
    """Small in-process model factory registry.

    Example:
        `registry.create("naive_return", {})`
    """

    _factories: dict[str, ModelFactory] = field(default_factory=dict)

    def register(self, name: str, factory: ModelFactory) -> None:
        """Register a model factory by stable name."""
        if not name.strip():
            raise ValueError("Invalid model name ''; expected non-empty name")
        self._factories[name] = factory

    def create(
        self,
        name: str,
        config: Mapping[str, object] | None = None,
    ) -> BaseForecastModel:
        """Create a model by registered name."""
        try:
            return self._factories[name](dict(config or {}))
        except KeyError as exc:
            raise ValueError(
                f"Invalid model {name!r}; expected one of {self.names()!r}"
            ) from exc

    def names(self) -> tuple[str, ...]:
        """Return registered model names."""
        return tuple(sorted(self._factories))


def build_default_model_registry() -> ForecastModelRegistry:
    """Build the default CPU-first forecast model registry."""
    from src.models.pretrained.chronos_adapter import ChronosAdapter
    from src.models.pretrained.neuralprophet_adapter import NeuralProphetAdapter
    from src.models.pretrained.patchtst_adapter import PatchTSTAdapter
    from src.models.pretrained.timesfm_adapter import TimesFMAdapter
    from src.models.sequence.fin_mamba import FinMambaBlock, FinMambaConfig
    from src.models.sequence.gru_attention import GRUAttentionBlock, GRUAttentionConfig
    from src.models.sequence.samba_block import SambaForecastModel
    from src.models.sequence.tcn import TCNBlock, TCNConfig

    def _fin_mamba_from_config(config):
        return FinMambaBlock(FinMambaConfig(
            input_dim=int(config.get("input_dim", 4)),
            hidden_dim=int(config.get("hidden_dim", 32)),
            num_layers=int(config.get("num_layers", 1)),
            dropout=float(config.get("dropout", 0.0)),
            horizon=int(config.get("horizon", 1)),
        )).build()

    def _tcn_from_config(config):
        return TCNBlock(TCNConfig(
            input_dim=int(config.get("input_dim", 4)),
            hidden_dim=int(config.get("hidden_dim", 32)),
            output_dim=int(config.get("output_dim", 1)),
            kernel_size=int(config.get("kernel_size", 3)),
            layers=int(config.get("num_layers", 1)),
            dropout=float(config.get("dropout", 0.0)),
        )).build()

    def _gru_attention_from_config(config):
        return GRUAttentionBlock(GRUAttentionConfig(
            input_dim=int(config.get("input_dim", 4)),
            hidden_dim=int(config.get("hidden_dim", 32)),
            output_dim=int(config.get("output_dim", 1)),
            layers=int(config.get("num_layers", 1)),
            dropout=float(config.get("dropout", 0.0)),
        )).build()

    registry = ForecastModelRegistry()
    registry.register("naive_return", lambda config: NaiveReturnBaseline())
    registry.register(
        "ridge_return",
        lambda config: RidgeReturnBaseline(alpha=float(config.get("alpha", 1.0))),
    )
    registry.register(
        "lightgbm",
        lambda config: OptionalBoostedBaseline("lightgbm"),
    )
    registry.register(
        "xgboost",
        lambda config: OptionalBoostedBaseline("xgboost"),
    )
    registry.register(
        "neuralprophet",
        lambda config: NeuralProphetAdapter.from_config(config),
    )
    registry.register("chronos", lambda config: ChronosAdapter.from_config(config))
    registry.register("patchtst", lambda config: PatchTSTAdapter.from_config(config))
    registry.register("timesfm", lambda config: TimesFMAdapter.from_config(config))
    registry.register("samba", lambda config: SambaForecastModel.from_config(config))
    registry.register("fin_mamba", _fin_mamba_from_config)
    registry.register("tcn", _tcn_from_config)
    registry.register("gru_attention", _gru_attention_from_config)
    registry.register(
        "samba_forecast",
        lambda config: SambaForecastModel.from_config(config),
    )
    return registry


def model_artifact_record(
    model_name: str,
    model_version: str,
    artifact_uri: str,
    metadata: Mapping[str, object] | None = None,
) -> dict[str, object]:
    """Return a `model_artifacts` row payload."""
    return {
        "model_name": model_name,
        "model_version": model_version,
        "artifact_uri": artifact_uri,
        "metadata_json": dict(metadata or {}),
    }


def register_model_artifact(
    database_url: str,
    model_name: str,
    model_version: str,
    artifact_uri: str,
    metadata: Mapping[str, object] | None = None,
) -> dict[str, object]:
    """Insert or update model artifact metadata in SQLite/Postgres."""
    from sqlalchemy import create_engine, delete, insert

    from src.database.core_schema import model_artifacts

    record = model_artifact_record(model_name, model_version, artifact_uri, metadata)
    engine = create_engine(database_url)
    try:
        with engine.begin() as connection:
            connection.execute(
                delete(model_artifacts).where(
                    model_artifacts.c.model_name == model_name,
                    model_artifacts.c.model_version == model_version,
                )
            )
            connection.execute(insert(model_artifacts).values(**record))
    finally:
        engine.dispose()
    return record


def save_model_with_registry_metadata(
    model: BaseForecastModel,
    path: str | Path,
) -> dict[str, Any]:
    """Save a model and write a sidecar metadata file."""
    artifact_path = model.save(path)
    metadata = model.metadata() | {"artifact_path": str(artifact_path)}
    sidecar_path = artifact_path.with_suffix(artifact_path.suffix + ".metadata.json")
    sidecar_path.write_text(json.dumps(metadata, sort_keys=True, indent=2))
    return metadata
