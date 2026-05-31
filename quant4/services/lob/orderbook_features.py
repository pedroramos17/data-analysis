"""Leakage-safe order-book feature generation."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from quant4.services.lob.parser import LOBSnapshot
from quant4.services.lob.queue_features import (
    book_resilience,
    depth_imbalance,
    queue_imbalance,
)

FEATURE_COLUMNS = [
    "best_bid",
    "best_ask",
    "mid_price",
    "spread",
    "microprice",
    "weighted_mid",
    "order_imbalance",
    "depth_imbalance",
    "queue_imbalance",
    "slope_of_book",
    "bid_pressure",
    "ask_pressure",
    "realized_spread",
    "effective_spread",
    "price_impact",
    "book_resilience",
]


@dataclass(frozen=True, slots=True)
class OrderBookFeatureRow:
    """Feature vector with timestamps that contributed to it.

    Example:
        `OrderBookFeatureRow("t0", "BTC", {"mid_price": 1.0}, ["t0"])`
    """

    timestamp: str
    symbol: str
    values: dict[str, float]
    source_timestamps: list[str]


@dataclass(frozen=True, slots=True)
class FeatureTensor:
    """Ordered feature matrix for local baseline models.

    Example:
        `FeatureTensor(["t0"], ["mid_price"], [[100.0]])`
    """

    timestamps: list[str]
    columns: list[str]
    rows: list[list[float]]


def build_orderbook_features(
    snapshots: Sequence[LOBSnapshot],
    lookback: int = 1,
) -> list[OrderBookFeatureRow]:
    """Build past-only LOB features for every snapshot.

    Example:
        `build_orderbook_features(snapshots, lookback=3)`
    """
    ordered = _ordered_snapshots(snapshots)
    return [_feature_row(ordered, index, lookback) for index in range(len(ordered))]


def build_feature_tensor(snapshots: Sequence[LOBSnapshot]) -> FeatureTensor:
    """Return an ordered tensor with stable feature columns.

    Example:
        `build_feature_tensor(snapshots).columns`
    """
    features = build_orderbook_features(snapshots)
    rows = [[row.values[column] for column in FEATURE_COLUMNS] for row in features]
    return FeatureTensor(
        [row.timestamp for row in features],
        list(FEATURE_COLUMNS),
        rows,
    )


def _feature_row(
    snapshots: Sequence[LOBSnapshot],
    index: int,
    lookback: int,
) -> OrderBookFeatureRow:
    start = max(0, index - max(lookback, 1) + 1)
    window = snapshots[start : index + 1]
    current = snapshots[index]
    values = _features_for_snapshot(current, window)
    return OrderBookFeatureRow(
        current.timestamp,
        current.symbol,
        values,
        [snapshot.timestamp for snapshot in window],
    )


def _features_for_snapshot(
    snapshot: LOBSnapshot,
    window: Sequence[LOBSnapshot],
) -> dict[str, float]:
    base = _base_prices(snapshot)
    sizes = _depth_values(snapshot)
    return base | sizes | _spread_features(snapshot, window, base)


def _base_prices(snapshot: LOBSnapshot) -> dict[str, float]:
    bid, ask = snapshot.bids[0][0], snapshot.asks[0][0]
    bid_size, ask_size = snapshot.bids[0][1], snapshot.asks[0][1]
    return {
        "best_bid": bid,
        "best_ask": ask,
        "mid_price": (bid + ask) / 2.0,
        "spread": ask - bid,
        "microprice": _safe_weighted_price(bid, ask, ask_size, bid_size),
        "weighted_mid": _visible_weighted_mid(snapshot),
    }


def _depth_values(snapshot: LOBSnapshot) -> dict[str, float]:
    bid_depth = sum(size for _, size in snapshot.bids)
    ask_depth = sum(size for _, size in snapshot.asks)
    total_depth = max(bid_depth + ask_depth, 1e-12)
    return {
        "order_imbalance": depth_imbalance(snapshot),
        "depth_imbalance": depth_imbalance(snapshot),
        "queue_imbalance": queue_imbalance(snapshot),
        "slope_of_book": _slope_of_book(snapshot),
        "bid_pressure": bid_depth / total_depth,
        "ask_pressure": ask_depth / total_depth,
    }


def _spread_features(
    snapshot: LOBSnapshot,
    window: Sequence[LOBSnapshot],
    base: Mapping[str, float],
) -> dict[str, float]:
    trade_price = float(snapshot.metadata.get("trade_price", base["mid_price"]))
    previous_mid = _previous_mid(window)
    return {
        "realized_spread": 2.0 * (trade_price - base["mid_price"]),
        "effective_spread": 2.0 * abs(trade_price - base["mid_price"]),
        "price_impact": base["mid_price"] - previous_mid,
        "book_resilience": book_resilience(window),
    }


def _visible_weighted_mid(snapshot: LOBSnapshot) -> float:
    levels = list(snapshot.bids) + list(snapshot.asks)
    total_size = sum(size for _, size in levels)
    return sum(price * size for price, size in levels) / max(total_size, 1e-12)


def _safe_weighted_price(
    bid: float,
    ask: float,
    bid_weight: float,
    ask_weight: float,
) -> float:
    return (bid * bid_weight + ask * ask_weight) / max(bid_weight + ask_weight, 1e-12)


def _slope_of_book(snapshot: LOBSnapshot) -> float:
    bid_slope = snapshot.bids[0][0] - snapshot.bids[-1][0]
    ask_slope = snapshot.asks[-1][0] - snapshot.asks[0][0]
    depth = len(snapshot.bids) + len(snapshot.asks)
    return (bid_slope + ask_slope) / max(depth, 1)


def _previous_mid(window: Sequence[LOBSnapshot]) -> float:
    if len(window) < 2:
        return _mid_price(window[-1])
    return _mid_price(window[-2])


def _mid_price(snapshot: LOBSnapshot) -> float:
    return (snapshot.bids[0][0] + snapshot.asks[0][0]) / 2.0


def _ordered_snapshots(snapshots: Sequence[LOBSnapshot]) -> list[LOBSnapshot]:
    return sorted(snapshots, key=lambda snapshot: snapshot.timestamp)
