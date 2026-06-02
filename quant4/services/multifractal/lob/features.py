"""Feature transforms from Quant4 LOB snapshots to multifractal series."""

from __future__ import annotations

from datetime import datetime
from typing import TypedDict

from quant4.services.lob.parser import LOBSnapshot
from quant4.services.multifractal.lob.contracts import (
    LOBMultifractalSeries,
    validate_lob_series,
)


class LOBMultifractalFeatureRow(TypedDict):
    """Typed row for observed LOB multifractal features."""

    source_timestamp: str
    spread: float
    order_imbalance: float
    bid_depth: float
    ask_depth: float
    inter_event_duration: float


def build_lob_mf_features(
    snapshots: list[LOBSnapshot],
) -> list[LOBMultifractalFeatureRow]:
    """Build observed-only LOB feature rows.

    Example:
        `rows = build_lob_mf_features(snapshots)`
    """
    ordered = _ordered_snapshots(snapshots)
    return [_feature_row(ordered, index) for index in range(len(ordered))]


def build_lob_mf_series(snapshots: list[LOBSnapshot]) -> LOBMultifractalSeries:
    """Return aligned LOB series for MF-DFA, partition, and MF-DCCA."""
    rows = build_lob_mf_features(snapshots)
    series = LOBMultifractalSeries(
        timestamps=tuple(row["source_timestamp"] for row in rows),
        spread=tuple(row["spread"] for row in rows),
        imbalance=tuple(row["order_imbalance"] for row in rows),
        bid_depth=tuple(row["bid_depth"] for row in rows),
        ask_depth=tuple(row["ask_depth"] for row in rows),
        inter_event_duration=tuple(row["inter_event_duration"] for row in rows),
    )
    validate_lob_series(series)
    return series


def _feature_row(
    snapshots: list[LOBSnapshot],
    index: int,
) -> LOBMultifractalFeatureRow:
    current = snapshots[index]
    bid_depth = _depth(current.bids)
    ask_depth = _depth(current.asks)
    return {
        "source_timestamp": current.timestamp,
        "spread": current.asks[0][0] - current.bids[0][0],
        "order_imbalance": _safe_ratio(bid_depth - ask_depth, bid_depth + ask_depth),
        "bid_depth": bid_depth,
        "ask_depth": ask_depth,
        "inter_event_duration": _duration(snapshots, index),
    }


def _duration(snapshots: list[LOBSnapshot], index: int) -> float:
    if index == 0:
        return 1.0
    current = _timestamp_seconds(snapshots[index].timestamp)
    previous = _timestamp_seconds(snapshots[index - 1].timestamp)
    return max(current - previous, 1e-9)


def _timestamp_seconds(value: str) -> float:
    try:
        return datetime.fromisoformat(value).timestamp()
    except ValueError:
        return float(len(value))


def _depth(levels: tuple[tuple[float, float], ...]) -> float:
    return sum(size for _price, size in levels)


def _safe_ratio(numerator: float, denominator: float) -> float:
    if denominator == 0.0:
        return 0.0
    return numerator / denominator


def _ordered_snapshots(snapshots: list[LOBSnapshot]) -> list[LOBSnapshot]:
    if snapshots:
        return sorted(snapshots, key=lambda snapshot: snapshot.timestamp)
    raise ValueError(f"Invalid snapshots {snapshots!r}; expected non-empty list")
