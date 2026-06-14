"""Horizon-aware LOB label generation."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from quant.services.lob.parser import LOBSnapshot


@dataclass(frozen=True, slots=True)
class LOBLabelRow:
    """Label vector aligned to one LOB feature timestamp.

    Example:
        `LOBLabelRow("t0", "BTC", {"h_step_direction": 1}, 5)`
    """

    timestamp: str
    symbol: str
    values: dict[str, float]
    horizon: int


def build_lob_labels(
    snapshots: Sequence[LOBSnapshot],
    horizon: int = 1,
) -> list[LOBLabelRow]:
    """Build future-label rows while keeping features separate.

    Example:
        `build_lob_labels(snapshots, horizon=5)`
    """
    if horizon < 1:
        raise ValueError(f"Invalid horizon {horizon!r}; expected positive integer")
    ordered = sorted(snapshots, key=lambda snapshot: snapshot.timestamp)
    return [_label_row(ordered, index, horizon) for index in range(len(ordered))]


def _label_row(
    snapshots: Sequence[LOBSnapshot],
    index: int,
    horizon: int,
) -> LOBLabelRow:
    current = snapshots[index]
    next_snapshot = snapshots[min(index + 1, len(snapshots) - 1)]
    target = snapshots[min(index + horizon, len(snapshots) - 1)]
    values = _label_values(snapshots, index, current, next_snapshot, target)
    return LOBLabelRow(current.timestamp, current.symbol, values, horizon)


def _label_values(
    snapshots: Sequence[LOBSnapshot],
    index: int,
    current: LOBSnapshot,
    next_snapshot: LOBSnapshot,
    target: LOBSnapshot,
) -> dict[str, float]:
    current_mid, target_mid = _mid_price(current), _mid_price(target)
    future_mids = [_mid_price(row) for row in snapshots[index : index + 2]]
    return {
        "next_mid_movement": float(_direction(_mid_price(next_snapshot) - current_mid)),
        "h_step_return": _safe_return(current_mid, target_mid),
        "h_step_direction": float(_direction(target_mid - current_mid)),
        "spread_widening": float(_spread(target) > _spread(current)),
        "liquidity_vacuum": float(
            _visible_depth(target) < _visible_depth(current) * 0.5
        ),
        "short_horizon_drawdown": _drawdown(current_mid, future_mids),
        "execution_cost_estimate": _spread(current) / max(current_mid, 1e-12),
    }


def _direction(value: float) -> int:
    if value > 0:
        return 1
    if value < 0:
        return -1
    return 0


def _safe_return(current_mid: float, target_mid: float) -> float:
    return (target_mid - current_mid) / max(current_mid, 1e-12)


def _drawdown(current_mid: float, future_mids: Sequence[float]) -> float:
    return min((mid - current_mid) / max(current_mid, 1e-12) for mid in future_mids)


def _mid_price(snapshot: LOBSnapshot) -> float:
    return (snapshot.bids[0][0] + snapshot.asks[0][0]) / 2.0


def _spread(snapshot: LOBSnapshot) -> float:
    return snapshot.asks[0][0] - snapshot.bids[0][0]


def _visible_depth(snapshot: LOBSnapshot) -> float:
    return sum(size for _, size in snapshot.bids + snapshot.asks)
