"""Local fallback regime detectors for Quant."""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from statistics import mean, pstdev


@dataclass(frozen=True, slots=True)
class RegimeLabel:
    """One leakage-safe regime label.

    Example:
        `RegimeLabel(0, "calm", 0, {"volatility": 0.0})`
    """

    index: int
    label: str
    training_end_index: int
    metrics: Mapping[str, object]


def rolling_volatility_regime(
    returns: Sequence[float],
    window: int = 20,
    high_threshold: float = 0.03,
) -> list[RegimeLabel]:
    """Label each point using only returns up to that point.

    Example:
        `rolling_volatility_regime([0.01, -0.02], window=2)`
    """
    labels: list[RegimeLabel] = []
    for index in range(len(returns)):
        sample = _past_window(returns, index, window)
        volatility = pstdev(sample) if len(sample) > 1 else 0.0
        label = "volatile" if volatility >= high_threshold else "calm"
        labels.append(_label(index, label, {"volatility": volatility}))
    return labels


def drawdown_regime(
    prices: Sequence[float],
    threshold: float = -0.10,
) -> list[RegimeLabel]:
    """Label drawdown pressure from past price peaks only.

    Example:
        `drawdown_regime([100, 95, 90])`
    """
    labels: list[RegimeLabel] = []
    peak = prices[0] if prices else 0.0
    for index, price in enumerate(prices):
        peak = max(peak, price)
        drawdown = _safe_ratio(price - peak, peak)
        label = _drawdown_label(drawdown, threshold)
        labels.append(_label(index, label, {"drawdown": drawdown}))
    return labels


def return_distribution_regime(
    returns: Sequence[float],
    window: int = 20,
) -> list[RegimeLabel]:
    """Label skew-like pressure from past return distribution only.

    Example:
        `return_distribution_regime([0.01, -0.04, 0.02])`
    """
    labels: list[RegimeLabel] = []
    for index in range(len(returns)):
        sample = _past_window(returns, index, window)
        center = mean(sample) if sample else 0.0
        label = "left_tail" if center < 0 else "balanced"
        labels.append(_label(index, label, {"mean_return": center}))
    return labels


def tda_entropy_regime(
    values: Sequence[float],
    window: int = 20,
    bins: int = 4,
) -> list[RegimeLabel]:
    """Return a histogram-entropy fallback when TDA libraries are absent.

    Example:
        `tda_entropy_regime([1.0, 2.0, 3.0])`
    """
    labels: list[RegimeLabel] = []
    for index in range(len(values)):
        entropy = _histogram_entropy(_past_window(values, index, window), bins)
        regime = "complex" if entropy > 1.0 else "simple"
        metrics = {"entropy": entropy, "method": "histogram"}
        labels.append(_label(index, regime, metrics))
    return labels


def graph_density_regime() -> dict[str, object]:
    """Return graph-density regime metadata from the latest graph snapshot.

    Example:
        `graph_density_regime()`
    """
    from quant.models import GraphSnapshot

    snapshot = GraphSnapshot.objects.order_by("-created_at").first()
    if snapshot is None:
        return {"label": "no_graph", "density": 0.0, "available": False}
    density = _graph_density(snapshot.node_count, snapshot.edge_count)
    return {"label": _density_label(density), "density": density, "available": True}


def lob_liquidity_regime(
    lob_rows: Sequence[Mapping[str, object]] = (),
) -> dict[str, object]:
    """Return a liquidity regime stub when LOB rows are present.

    Example:
        `lob_liquidity_regime([])`
    """
    if not lob_rows:
        return {"label": "no_lob", "available": False, "method": "stub"}
    spread = mean(float(row.get("spread", 0.0) or 0.0) for row in lob_rows)
    return {"label": _spread_label(spread), "available": True, "average_spread": spread}


def regime_summary(
    returns: Sequence[float],
    prices: Sequence[float],
) -> dict[str, object]:
    """Build a compact multi-detector regime summary.

    Example:
        `regime_summary([0.01], [100.0])`
    """
    return {
        "rolling_volatility": _last_label(rolling_volatility_regime(returns)),
        "drawdown": _last_label(drawdown_regime(prices)),
        "return_distribution": _last_label(return_distribution_regime(returns)),
        "tda_entropy": _last_label(tda_entropy_regime(returns)),
        "graph_density": graph_density_regime(),
        "lob_liquidity": lob_liquidity_regime(),
    }


def _past_window(values: Sequence[float], index: int, window: int) -> list[float]:
    start = max(0, index - max(1, window) + 1)
    return [float(value) for value in values[start : index + 1]]


def _label(index: int, label: str, metrics: Mapping[str, object]) -> RegimeLabel:
    return RegimeLabel(
        index=index,
        label=label,
        training_end_index=index,
        metrics=metrics,
    )


def _drawdown_label(drawdown: float, threshold: float) -> str:
    return "drawdown" if drawdown <= threshold else "normal"


def _density_label(density: float) -> str:
    return "dense_graph" if density >= 0.25 else "sparse_graph"


def _spread_label(spread: float) -> str:
    return "wide_spread" if spread > 0.01 else "normal_spread"


def _graph_density(nodes: int, edges: int) -> float:
    possible_edges = nodes * max(0, nodes - 1)
    return _safe_ratio(edges, possible_edges)


def _safe_ratio(numerator: float, denominator: float) -> float:
    if denominator == 0:
        return 0.0
    return numerator / denominator


def _histogram_entropy(values: Sequence[float], bins: int) -> float:
    if not values:
        return 0.0
    counts = _histogram_counts(values, max(1, bins))
    return -sum(_entropy_term(count, len(values)) for count in counts if count)


def _histogram_counts(values: Sequence[float], bins: int) -> list[int]:
    low = min(values)
    high = max(values)
    if low == high:
        return [len(values)]
    counts = [0 for _ in range(bins)]
    for value in values:
        bucket = min(bins - 1, int((value - low) / (high - low) * bins))
        counts[bucket] += 1
    return counts


def _entropy_term(count: int, total: int) -> float:
    probability = count / total
    return probability * math.log(probability, 2)


def _last_label(labels: Sequence[RegimeLabel]) -> dict[str, object]:
    if not labels:
        return {"label": "empty", "available": False}
    last = labels[-1]
    return {"label": last.label, "available": True, "metrics": dict(last.metrics)}
