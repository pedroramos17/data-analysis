"""Simple research-only backtester for Phase 8 predictions."""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime

from src.config.settings import DatabaseSettings
from src.pipeline.training.metrics import max_drawdown, sharpe_like, turnover_proxy


@dataclass(frozen=True, slots=True)
class BacktestResult:
    """Simple long/short signal backtest result."""

    trades: int
    cumulative_return: float
    average_return: float
    sharpe_like: float
    max_drawdown: float
    turnover_proxy: float
    hit_ratio: float

    def to_dict(self) -> dict[str, object]:
        return {
            "trades": self.trades,
            "cumulative_return": self.cumulative_return,
            "average_return": self.average_return,
            "sharpe_like": self.sharpe_like,
            "max_drawdown": self.max_drawdown,
            "turnover_proxy": self.turnover_proxy,
            "hit_ratio": self.hit_ratio,
        }


def run_simple_backtest(rows: Sequence[Mapping[str, object]], threshold: float = 0.0) -> BacktestResult:
    """Simulate a simple sign(signal) strategy against y_true returns."""
    pnl: list[float] = []
    equity: list[float] = []
    signals: list[float] = []
    capital = 1.0
    hits = 0
    for row in rows:
        signal = _float(row.get("signal", row.get("y_pred")))
        target = _float(row.get("y_true"))
        position = 1.0 if signal > threshold else -1.0 if signal < -threshold else 0.0
        result = position * target
        if result > 0:
            hits += 1
        pnl.append(result)
        capital *= 1.0 + result
        equity.append(capital)
        signals.append(position)
    trades = sum(1 for value in signals if value != 0.0)
    return BacktestResult(
        trades=trades,
        cumulative_return=capital - 1.0,
        average_return=sum(pnl) / max(len(pnl), 1),
        sharpe_like=sharpe_like(pnl),
        max_drawdown=max_drawdown(equity),
        turnover_proxy=turnover_proxy(signals),
        hit_ratio=hits / max(trades, 1),
    )


def run_backtest_from_predictions(rows: Sequence[Mapping[str, object]], config: Mapping[str, object]) -> dict[str, object]:
    """Backtest prediction rows and return JSON-safe metrics."""
    threshold = float(config.get("signal_threshold") or config.get("threshold") or 0.0)
    return run_simple_backtest(rows, threshold).to_dict()


def register_backtest_metrics(
    database_settings: DatabaseSettings,
    name: str,
    config: Mapping[str, object],
    metrics: Mapping[str, object],
) -> int | None:
    """Persist backtest metrics into backtest_runs."""
    if database_settings.db_mode == "sqlite":
        database_settings.sqlite_path.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(database_settings.sqlite_path) as connection:
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
    return None


def _float(value: object) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0
