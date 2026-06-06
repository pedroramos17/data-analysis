"""Risk reporting for Phase 8 evaluation windows."""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime

from src.config.settings import DatabaseSettings
from src.pipeline.training.metrics import max_drawdown, sharpe_like


@dataclass(frozen=True, slots=True)
class RiskReport:
    """Risk report for prediction or strategy returns."""

    observations: int
    mean_return: float
    volatility: float
    value_at_risk_95: float
    expected_shortfall_95: float
    max_drawdown: float
    sharpe_like: float
    gross_exposure: float
    net_exposure: float

    def to_dict(self) -> dict[str, object]:
        return {
            "observations": self.observations,
            "mean_return": self.mean_return,
            "volatility": self.volatility,
            "value_at_risk_95": self.value_at_risk_95,
            "expected_shortfall_95": self.expected_shortfall_95,
            "max_drawdown": self.max_drawdown,
            "sharpe_like": self.sharpe_like,
            "gross_exposure": self.gross_exposure,
            "net_exposure": self.net_exposure,
        }


def compute_risk_report(rows: Sequence[Mapping[str, object]]) -> RiskReport:
    """Compute risk metrics from Phase 8 prediction rows."""
    returns = [_position(row) * _float(row.get("y_true")) for row in rows]
    exposures = [_position(row) for row in rows]
    equity = _equity_curve(returns)
    sorted_returns = sorted(returns)
    var_index = int(max(0, min(len(sorted_returns) - 1, round(0.05 * max(len(sorted_returns) - 1, 0))))) if sorted_returns else 0
    var = sorted_returns[var_index] if sorted_returns else 0.0
    shortfall_values = [value for value in sorted_returns if value <= var]
    mean = sum(returns) / max(len(returns), 1)
    volatility = _std(returns)
    return RiskReport(
        observations=len(rows),
        mean_return=mean,
        volatility=volatility,
        value_at_risk_95=var,
        expected_shortfall_95=sum(shortfall_values) / max(len(shortfall_values), 1),
        max_drawdown=max_drawdown(equity),
        sharpe_like=sharpe_like(returns),
        gross_exposure=sum(abs(value) for value in exposures) / max(len(exposures), 1),
        net_exposure=sum(exposures) / max(len(exposures), 1),
    )


def register_risk_metrics(
    database_settings: DatabaseSettings,
    universe: str,
    config: Mapping[str, object],
    metrics: Mapping[str, object],
) -> int | None:
    """Persist risk metrics into risk_runs."""
    if database_settings.db_mode != "sqlite":
        return None
    database_settings.sqlite_path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(database_settings.sqlite_path) as connection:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS risk_runs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                universe TEXT NOT NULL,
                config_json TEXT NOT NULL DEFAULT '{}',
                metrics_json TEXT NOT NULL DEFAULT '{}',
                created_at TEXT NOT NULL
            )
            """
        )
        cursor = connection.execute(
            "INSERT INTO risk_runs (universe, config_json, metrics_json, created_at) VALUES (?, ?, ?, ?)",
            (
                universe,
                json.dumps(dict(config), sort_keys=True, default=str),
                json.dumps(dict(metrics), sort_keys=True, default=str),
                datetime.now(UTC).isoformat(),
            ),
        )
        return int(cursor.lastrowid)


def _equity_curve(returns: Sequence[float]) -> list[float]:
    capital = 1.0
    output: list[float] = []
    for value in returns:
        capital *= 1.0 + value
        output.append(capital)
    return output


def _position(row: Mapping[str, object]) -> float:
    signal = _float(row.get("signal", row.get("y_pred")))
    return 1.0 if signal > 0 else -1.0 if signal < 0 else 0.0


def _std(values: Sequence[float]) -> float:
    if len(values) < 2:
        return 0.0
    mean = sum(values) / len(values)
    variance = sum((value - mean) ** 2 for value in values) / (len(values) - 1)
    return variance**0.5


def _float(value: object) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0
