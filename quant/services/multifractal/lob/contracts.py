"""Contracts for multifractal-ready LOB series."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class LOBMultifractalSeries:
    """Aligned LOB series used by multifractal methods.

    Example:
        `series = LOBMultifractalSeries(["t0"], [0.01], [0.2], [1.0], [2.0])`
    """

    timestamps: tuple[str, ...]
    spread: tuple[float, ...]
    imbalance: tuple[float, ...]
    bid_depth: tuple[float, ...]
    ask_depth: tuple[float, ...]
    inter_event_duration: tuple[float, ...]


def validate_lob_series(series: LOBMultifractalSeries) -> None:
    """Validate that LOB series are aligned and non-empty."""
    lengths = _lengths(series)
    if len(set(lengths)) == 1 and lengths[0] > 0:
        return
    raise ValueError(f"Invalid LOB series lengths {lengths!r}; expected equal > 0")


def _lengths(series: LOBMultifractalSeries) -> tuple[int, ...]:
    values: Sequence[Sequence[object]] = (
        series.timestamps,
        series.spread,
        series.imbalance,
        series.bid_depth,
        series.ask_depth,
        series.inter_event_duration,
    )
    return tuple(len(value) for value in values)
