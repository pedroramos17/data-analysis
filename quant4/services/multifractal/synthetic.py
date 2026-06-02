"""Synthetic data generators for Quant4 multifractal tests and demos."""

from __future__ import annotations

import math
import random

from quant4.services.lob.parser import LOBSnapshot


def gaussian_random_walk(length: int, seed: int = 17) -> list[float]:
    """Return a seeded Gaussian random walk price-like series.

    Example:
        `series = gaussian_random_walk(128, seed=7)`
    """
    _positive_int(length, "length")
    chooser = random.Random(seed)
    value = 100.0
    series: list[float] = []
    for _index in range(length):
        value *= math.exp(chooser.gauss(0.0, 0.01))
        series.append(value)
    return series


def fractional_like_noise(length: int, seed: int = 17) -> list[float]:
    """Return a lightweight autocorrelated noise placeholder.

    Example:
        `noise = fractional_like_noise(128, seed=7)`
    """
    _positive_int(length, "length")
    chooser = random.Random(seed)
    previous = 0.0
    values: list[float] = []
    for _index in range(length):
        previous = 0.75 * previous + chooser.gauss(0.0, 0.01)
        values.append(previous)
    return values


def multiplicative_cascade(levels: int, seed: int = 17) -> list[float]:
    """Return a positive binomial-like multiplicative cascade.

    Example:
        `measure = multiplicative_cascade(6, seed=7)`
    """
    _positive_int(levels, "levels")
    chooser = random.Random(seed)
    weights = [1.0]
    for _level in range(levels):
        weights = _split_cascade_weights(weights, chooser)
    return weights


def regime_switching_volatility(length: int, seed: int = 17) -> list[float]:
    """Return returns with deterministic low/high volatility regimes.

    Example:
        `returns = regime_switching_volatility(256, seed=7)`
    """
    _positive_int(length, "length")
    chooser = random.Random(seed)
    midpoint = max(1, length // 2)
    return [
        chooser.gauss(0.0, 0.006 if index < midpoint else 0.035)
        for index in range(length)
    ]


def heavy_tailed_returns(length: int, seed: int = 17) -> list[float]:
    """Return seeded heavy-tailed return-like values.

    Example:
        `returns = heavy_tailed_returns(128, seed=7)`
    """
    _positive_int(length, "length")
    chooser = random.Random(seed)
    return [
        chooser.gauss(0.0, 0.01) / max(chooser.random(), 0.08)
        for _index in range(length)
    ]


def price_volume_pair(length: int, seed: int = 17) -> tuple[list[float], list[float]]:
    """Return aligned synthetic price and volume series.

    Example:
        `prices, volumes = price_volume_pair(128, seed=7)`
    """
    prices = gaussian_random_walk(length, seed)
    chooser = random.Random(seed + 1)
    volumes = [1000.0 + abs(chooser.gauss(0.0, 120.0)) for _item in prices]
    return prices, volumes


def synthetic_lob_event_durations(length: int, seed: int = 17) -> list[float]:
    """Return positive synthetic LOB inter-event durations."""
    _positive_int(length, "length")
    chooser = random.Random(seed)
    return [max(chooser.expovariate(2.0), 1e-6) for _index in range(length)]


def synthetic_lob_snapshots(length: int, seed: int = 17) -> list[LOBSnapshot]:
    """Return deterministic LOB snapshots for local microstructure tests."""
    _positive_int(length, "length")
    chooser = random.Random(seed)
    return [_lob_snapshot(index, chooser) for index in range(length)]


def _split_cascade_weights(
    weights: list[float],
    chooser: random.Random,
) -> list[float]:
    expanded: list[float] = []
    for weight in weights:
        share = 0.35 + chooser.random() * 0.30
        expanded.extend([weight * share, weight * (1.0 - share)])
    return expanded


def _lob_snapshot(index: int, chooser: random.Random) -> LOBSnapshot:
    mid = 100.0 + index * 0.01 + chooser.gauss(0.0, 0.002)
    spread = 0.02 + (index % 5) * 0.001
    bid = mid - spread / 2.0
    ask = mid + spread / 2.0
    return LOBSnapshot(
        timestamp=f"2026-01-01T00:00:{index:02d}",
        symbol="SYNTH",
        bids=((bid, 10.0 + index), (bid - 0.01, 8.0)),
        asks=((ask, 9.0), (ask + 0.01, 7.0 + index * 0.5)),
        venue_type="synthetic",
        metadata={"event_type": "book"},
    )


def _positive_int(value: int, label: str) -> None:
    if isinstance(value, int) and value > 0:
        return
    raise ValueError(f"Invalid {label} {value!r}; expected positive integer")
