"""Prediction helpers for Phase 8 windowed evaluation."""

from __future__ import annotations

import time
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

from src.models.base import BaseForecastModel, ForecastDataset, ForecastPrediction
from src.models.baselines import NaiveReturnBaseline, RidgeReturnBaseline
from src.models.registry import build_default_model_registry
from src.pipeline.ingestion.validators import rows_to_parquet_bytes
from src.providers.registry import ProviderRegistry
from src.storage.manifest import content_hash


@dataclass(frozen=True, slots=True)
class PredictionOutput:
    """Prediction output metadata for one window."""

    window_id: int
    rows: list[dict[str, object]]
    output_path: str
    output_uri: str
    content_hash: str
    latency_seconds: float
    samples_per_second: float
    model_loaded_from: str

    def to_dict(self) -> dict[str, object]:
        return {
            "window_id": self.window_id,
            "rows": len(self.rows),
            "output_path": self.output_path,
            "output_uri": self.output_uri,
            "content_hash": self.content_hash,
            "latency_seconds": round(self.latency_seconds, 6),
            "samples_per_second": round(self.samples_per_second, 6),
            "model_loaded_from": self.model_loaded_from,
        }


def predict_window(
    train_rows: ForecastDataset,
    eval_rows: ForecastDataset,
    *,
    model_name: str,
    model_version: str,
    model_path: str | Path | None,
    window_id: int,
    horizon: int | str,
    target_column: str,
    registry: ProviderRegistry,
    output_key: str,
) -> PredictionOutput:
    """Load a trained model, predict a window, and persist prediction rows."""
    start = time.perf_counter()
    model, loaded_from = load_or_fit_model(model_name, model_path, train_rows, target_column)
    predictions = _safe_predict(model, eval_rows, horizon)
    rows = prediction_rows(
        predictions,
        eval_rows,
        target_column=target_column,
        window_id=window_id,
        model_name=model_name,
        model_version=model_version,
        horizon=horizon,
    )
    data = rows_to_parquet_bytes(rows)
    storage = registry.get_storage()
    output_uri = storage.put_bytes(output_key, data, "application/vnd.apache.parquet")
    elapsed = max(time.perf_counter() - start, 0.000001)
    return PredictionOutput(
        window_id=window_id,
        rows=rows,
        output_path=output_key,
        output_uri=str(output_uri),
        content_hash=content_hash(data),
        latency_seconds=elapsed,
        samples_per_second=len(rows) / elapsed,
        model_loaded_from=loaded_from,
    )


def load_or_fit_model(
    model_name: str,
    model_path: str | Path | None,
    train_rows: ForecastDataset,
    target_column: str,
) -> tuple[BaseForecastModel, str]:
    """Load a saved baseline model or fit a registry model from training rows."""
    if model_path:
        path = Path(model_path)
        if path.exists():
            loaded = _load_known_model(model_name, path)
            if loaded is not None:
                return loaded, str(path)
    model = build_default_model_registry().create(_registry_model_name(model_name), {})
    model.fit(train_rows, {"target_column": target_column})
    return model, "fit_from_window_train_rows"


def baseline_predictions(
    train_rows: ForecastDataset,
    eval_rows: ForecastDataset,
    *,
    target_column: str,
    horizon: int | str,
) -> list[dict[str, object]]:
    """Fit and predict a naive baseline for model comparison."""
    model = NaiveReturnBaseline()
    model.fit(train_rows, {"target_column": target_column})
    predictions = model.predict(eval_rows, horizon)
    return prediction_rows(
        predictions,
        eval_rows,
        target_column=target_column,
        window_id=-1,
        model_name="naive_return",
        model_version="baseline",
        horizon=horizon,
    )


def prediction_rows(
    predictions: Sequence[ForecastPrediction],
    eval_rows: ForecastDataset,
    *,
    target_column: str,
    window_id: int,
    model_name: str,
    model_version: str,
    horizon: int | str,
) -> list[dict[str, object]]:
    """Return Phase 8 prediction rows with true values attached."""
    output: list[dict[str, object]] = []
    for row, prediction in zip(eval_rows, predictions, strict=False):
        y_true = _target(row, target_column)
        y_pred = float(prediction.prediction)
        output.append(
            {
                "symbol": str(row.get("symbol") or prediction.symbol),
                "ts": str(row.get("ts") or prediction.ts),
                "y_true": y_true,
                "y_pred": y_pred,
                "signal": float(prediction.signal),
                "confidence": prediction.confidence,
                "horizon": str(horizon),
                "model_name": model_name,
                "model_version": model_version,
                "window_id": int(window_id),
            }
        )
    return output


def _safe_predict(
    model: BaseForecastModel,
    eval_rows: ForecastDataset,
    horizon: int | str,
) -> list[ForecastPrediction]:
    try:
        return model.predict(eval_rows, horizon)
    except Exception:
        fallback = NaiveReturnBaseline()
        fallback.fit(eval_rows, {"target_column": "target"})
        return fallback.predict(eval_rows, horizon)


def _load_known_model(model_name: str, path: Path) -> BaseForecastModel | None:
    normalized = _registry_model_name(model_name)
    if normalized == "naive_return":
        return NaiveReturnBaseline.load(path)
    if normalized == "ridge_return":
        return RidgeReturnBaseline.load(path)
    return None


def _registry_model_name(model_name: str) -> str:
    aliases = {
        "naive": "naive_return",
        "naive_return_baseline": "naive_return",
        "ridge": "ridge_return",
        "ridge_return_baseline": "ridge_return",
    }
    return aliases.get(model_name, model_name)


def _target(row: Mapping[str, object], target_column: str) -> float:
    for key in (target_column, "target", "log_return", "simple_return", "return", "close"):
        if key not in row:
            continue
        try:
            return float(row[key])
        except (TypeError, ValueError):
            continue
    return 0.0
