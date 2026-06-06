"""Batch prediction, Parquet export, and SQL signal persistence."""

from __future__ import annotations

import json
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from src.models.base import BaseForecastModel, ForecastDataset, ForecastPrediction
from src.models.explainability import (
    enrich_prediction_explanations,
    ensure_signal_explanation,
)


@dataclass(frozen=True, slots=True)
class PredictionBatchResult:
    """Result metadata for a batch prediction run."""

    predictions: list[ForecastPrediction]
    explanations: dict[str, object]
    parquet_path: Path | None = None
    signal_count: int = 0


def run_batch_prediction(
    model: BaseForecastModel,
    dataset: ForecastDataset,
    horizon: int | str,
    *,
    output_path: str | Path | None = None,
    database_url: str | None = None,
    feature_set_version: str = "",
) -> PredictionBatchResult:
    """Run model predictions and optionally persist outputs."""
    predictions = model.predict(dataset, horizon)
    explanations = model.explain(dataset, predictions)
    predictions = enrich_prediction_explanations(
        model,
        dataset,
        predictions,
        explanations,
        feature_set_version=feature_set_version,
    )
    parquet_path = (
        write_predictions_parquet(predictions, output_path) if output_path else None
    )
    signal_count = insert_signals(database_url, predictions) if database_url else 0
    return PredictionBatchResult(predictions, explanations, parquet_path, signal_count)


def write_predictions_parquet(
    predictions: Sequence[ForecastPrediction],
    output_path: str | Path,
) -> Path:
    """Write prediction rows directly to Parquet using lazy PyArrow import."""
    try:
        import pyarrow as pa
        import pyarrow.parquet as pq
    except ImportError as exc:
        raise RuntimeError(
            "pyarrow is required to save prediction outputs to Parquet"
        ) from exc
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    rows = [_parquet_row(prediction) for prediction in predictions]
    pq.write_table(pa.Table.from_pylist(rows), path)
    return path


def insert_signals(
    database_url: str,
    predictions: Sequence[ForecastPrediction],
) -> int:
    """Insert prediction outputs into the compatibility `signals` table."""
    from sqlalchemy import create_engine, insert

    from src.database.core_schema import signals

    rows = [signal_row(prediction) for prediction in predictions]
    if not rows:
        return 0
    engine = create_engine(database_url)
    try:
        with engine.begin() as connection:
            connection.execute(insert(signals), rows)
    finally:
        engine.dispose()
    return len(rows)


def signal_row(prediction: ForecastPrediction) -> dict[str, object]:
    """Convert a forecast prediction to the compatibility `signals` schema."""
    if prediction.asset_id is None:
        raise ValueError(
            "Cannot persist signal without asset_id; expected dataset rows to carry "
            "the compatibility assets.id value"
        )
    return {
        "asset_id": prediction.asset_id,
        "ts": _signal_timestamp(prediction.ts),
        "model_name": prediction.model_name,
        "model_version": prediction.model_version,
        "horizon": prediction.horizon,
        "signal": prediction.signal,
        "confidence": prediction.confidence,
        "explanation_json": ensure_signal_explanation(prediction),
    }


def prediction_rows(
    predictions: Sequence[ForecastPrediction],
) -> list[dict[str, object]]:
    """Return row dictionaries for JSON, logs, or tests."""
    rows: list[dict[str, object]] = []
    for prediction in predictions:
        row = prediction.to_dict()
        row["explanation_json"] = ensure_signal_explanation(prediction)
        rows.append(row)
    return rows


def _parquet_row(prediction: ForecastPrediction) -> dict[str, object]:
    row = prediction.to_dict()
    row["explanation_json"] = json.dumps(
        ensure_signal_explanation(prediction),
        sort_keys=True,
    )
    return row


def _signal_timestamp(value: object) -> datetime:
    if isinstance(value, datetime):
        return value
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(
            f"Cannot persist signal with invalid ts={value!r}; expected ISO timestamp"
        ) from exc
