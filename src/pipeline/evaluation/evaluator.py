"""Evaluation metrics and metric persistence for Phase 8."""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from src.config.settings import DatabaseSettings
from src.pipeline.training.metrics import evaluate_all


@dataclass(frozen=True, slots=True)
class EvaluationComparison:
    """Model-vs-baseline comparison result."""

    model_metrics: dict[str, float]
    baseline_metrics: dict[str, float]
    model_better_than_baseline: bool
    warning: str

    def to_dict(self) -> dict[str, object]:
        return {
            "model_metrics": dict(self.model_metrics),
            "baseline_metrics": dict(self.baseline_metrics),
            "model_better_than_baseline": self.model_better_than_baseline,
            "warning": self.warning,
        }


def evaluate_predictions(
    prediction_rows: Sequence[Mapping[str, object]],
    baseline_rows: Sequence[Mapping[str, object]],
    *,
    latency_seconds: float = 0.0,
    gpu_hourly_cost: float = 0.0,
) -> EvaluationComparison:
    """Evaluate model predictions and compare against naive baseline."""
    y_true = [_float(row.get("y_true")) for row in prediction_rows]
    y_pred = [_float(row.get("y_pred")) for row in prediction_rows]
    baseline_pred = [_float(row.get("y_pred")) for row in baseline_rows]
    model_metrics = evaluate_all(y_pred, y_true, latency_seconds, 1, gpu_hourly_cost)
    baseline_metrics = evaluate_all(baseline_pred, y_true[: len(baseline_pred)], latency_seconds, 1, gpu_hourly_cost)
    model_mse = model_metrics.get("mse", float("inf"))
    baseline_mse = baseline_metrics.get("mse", float("inf"))
    better = model_mse < baseline_mse
    warning = "" if better else "model_not_better_than_naive_baseline"
    return EvaluationComparison(model_metrics, baseline_metrics, better, warning)


def aggregate_metrics(per_window: Sequence[Mapping[str, object]]) -> dict[str, object]:
    """Aggregate per-window metrics and stability diagnostics."""
    metric_rows = [dict(item.get("model_metrics", {})) for item in per_window]
    aggregate: dict[str, object] = {}
    for key in sorted({key for row in metric_rows for key in row}):
        values = [_float(row.get(key)) for row in metric_rows if key in row]
        if not values:
            continue
        mean = sum(values) / len(values)
        variance = sum((value - mean) ** 2 for value in values) / max(len(values) - 1, 1)
        aggregate[key] = {"mean": mean, "min": min(values), "max": max(values), "std": variance**0.5}
    warnings = [str(item.get("warning") or "") for item in per_window if item.get("warning")]
    return {
        "aggregate_metrics": aggregate,
        "stability_metrics": _stability(metric_rows),
        "warnings": warnings,
        "windows": len(per_window),
        "model_better_than_baseline_rate": _better_rate(per_window),
    }


def regime_conditional_metrics(prediction_rows: Sequence[Mapping[str, object]]) -> dict[str, object]:
    """Group metrics by a regime-like column when present."""
    groups: dict[str, list[Mapping[str, object]]] = {}
    for row in prediction_rows:
        regime = str(row.get("regime") or row.get("market_regime") or "unknown")
        groups.setdefault(regime, []).append(row)
    output: dict[str, object] = {}
    for regime, rows in groups.items():
        y_true = [_float(row.get("y_true")) for row in rows]
        y_pred = [_float(row.get("y_pred")) for row in rows]
        output[regime] = evaluate_all(y_pred, y_true)
    return output


def feature_drift(train_rows: Sequence[Mapping[str, object]], eval_rows: Sequence[Mapping[str, object]]) -> dict[str, float]:
    """Simple numeric mean drift between train and eval rows."""
    columns = sorted(_numeric_columns(train_rows) & _numeric_columns(eval_rows))
    return {column: _mean(eval_rows, column) - _mean(train_rows, column) for column in columns}


def prediction_drift(rows: Sequence[Mapping[str, object]]) -> dict[str, float]:
    """Prediction drift from first half to second half of a window."""
    values = [_float(row.get("y_pred")) for row in rows]
    midpoint = len(values) // 2
    if midpoint == 0:
        return {"mean_shift": 0.0, "abs_mean_shift": 0.0}
    left = sum(values[:midpoint]) / midpoint
    right_values = values[midpoint:]
    right = sum(right_values) / max(len(right_values), 1)
    shift = right - left
    return {"mean_shift": shift, "abs_mean_shift": abs(shift)}


def register_evaluation_metrics(
    database_settings: DatabaseSettings,
    name: str,
    config: Mapping[str, object],
    metrics: Mapping[str, object],
) -> int | None:
    """Persist evaluation metrics in backtest_runs for SQLite/Postgres."""
    if database_settings.db_mode == "sqlite":
        return _register_sqlite(database_settings.sqlite_path, name, config, metrics)
    return _register_sqlalchemy(database_settings, name, config, metrics)


def _register_sqlite(path: Path, name: str, config: Mapping[str, object], metrics: Mapping[str, object]) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(path) as connection:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS backtest_runs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                config_json TEXT NOT NULL DEFAULT '{}',
                metrics_json TEXT NOT NULL DEFAULT '{}',
                created_at TEXT NOT NULL
            )
            """
        )
        cursor = connection.execute(
            "INSERT INTO backtest_runs (name, config_json, metrics_json, created_at) VALUES (?, ?, ?, ?)",
            (
                name,
                json.dumps(dict(config), sort_keys=True, default=str),
                json.dumps(dict(metrics), sort_keys=True, default=str),
                datetime.now(UTC).isoformat(),
            ),
        )
        return int(cursor.lastrowid)


def _register_sqlalchemy(
    database_settings: DatabaseSettings,
    name: str,
    config: Mapping[str, object],
    metrics: Mapping[str, object],
) -> int | None:
    try:
        from sqlalchemy import create_engine, insert

        from src.database.core_schema import backtest_runs, create_core_tables, sqlalchemy_url_from_database_settings
    except ImportError as exc:
        raise RuntimeError("SQLAlchemy is required for Postgres evaluation metrics") from exc
    engine = create_engine(sqlalchemy_url_from_database_settings(database_settings))
    try:
        with engine.begin() as connection:
            create_core_tables(connection)
            result = connection.execute(insert(backtest_runs).values(name=name, config_json=dict(config), metrics_json=dict(metrics)))
            primary_key = result.inserted_primary_key
            return int(primary_key[0]) if primary_key else None
    finally:
        engine.dispose()


def _better_rate(per_window: Sequence[Mapping[str, object]]) -> float:
    if not per_window:
        return 0.0
    return sum(1 for item in per_window if item.get("model_better_than_baseline")) / len(per_window)


def _stability(metric_rows: Sequence[Mapping[str, object]]) -> dict[str, float]:
    values = [_float(row.get("mse")) for row in metric_rows if "mse" in row]
    if not values:
        return {"mse_std": 0.0, "mse_range": 0.0}
    mean = sum(values) / len(values)
    variance = sum((value - mean) ** 2 for value in values) / max(len(values) - 1, 1)
    return {"mse_std": variance**0.5, "mse_range": max(values) - min(values)}


def _numeric_columns(rows: Sequence[Mapping[str, object]]) -> set[str]:
    columns: set[str] = set()
    for row in rows[:10]:
        for key, value in row.items():
            try:
                float(value)
            except (TypeError, ValueError):
                continue
            columns.add(str(key))
    return columns - {"asset_id", "target", "y_true", "y_pred", "signal", "confidence", "window_id"}


def _mean(rows: Sequence[Mapping[str, object]], column: str) -> float:
    values = [_float(row.get(column)) for row in rows if column in row]
    return sum(values) / max(len(values), 1)


def _float(value: object) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0
