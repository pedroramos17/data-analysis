"""Queue and depth feature helpers for LOB snapshots."""

from __future__ import annotations

from collections.abc import Sequence

from quant.services.lob.parser import LOBSnapshot


def queue_imbalance(snapshot: LOBSnapshot) -> float:
    """Return top-of-book queue imbalance.

    Example:
        `queue_imbalance(snapshot)`
    """
    return _imbalance(_best_bid_size(snapshot), _best_ask_size(snapshot))


def depth_imbalance(snapshot: LOBSnapshot) -> float:
    """Return full visible-depth imbalance.

    Example:
        `depth_imbalance(snapshot)`
    """
    return _imbalance(_total_size(snapshot.bids), _total_size(snapshot.asks))


def book_resilience(window: Sequence[LOBSnapshot]) -> float:
    """Estimate spread resilience using only the past feature window.

    Example:
        `book_resilience([previous_snapshot, current_snapshot])`
    """
    if len(window) < 2:
        return 1.0
    previous, current = window[-2], window[-1]
    spread_change = abs(_spread(current) - _spread(previous))
    return max(0.0, 1.0 - spread_change / max(_spread(previous), 1e-12))


def _imbalance(left_value: float, right_value: float) -> float:
    total = left_value + right_value
    return 0.0 if total <= 0 else (left_value - right_value) / total


def _total_size(levels: Sequence[tuple[float, float]]) -> float:
    return sum(size for _, size in levels)


def _best_bid_size(snapshot: LOBSnapshot) -> float:
    return snapshot.bids[0][1]


def _best_ask_size(snapshot: LOBSnapshot) -> float:
    return snapshot.asks[0][1]


def _spread(snapshot: LOBSnapshot) -> float:
    return snapshot.asks[0][0] - snapshot.bids[0][0]
