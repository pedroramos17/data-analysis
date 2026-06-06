"""Timing helpers for efficiency profiling."""

from __future__ import annotations

import time
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class TimingSnapshot:
    """Wall-clock and CPU-time snapshot."""

    wall_seconds: float
    cpu_seconds: float


def timing_snapshot() -> TimingSnapshot:
    """Return current wall-clock and CPU-time counters."""
    return TimingSnapshot(time.perf_counter(), time.process_time())


def timing_delta(start: TimingSnapshot, end: TimingSnapshot | None = None) -> dict[str, float]:
    """Return elapsed wall-clock and CPU seconds."""
    active_end = end or timing_snapshot()
    return {
        "wall_clock_seconds": max(active_end.wall_seconds - start.wall_seconds, 0.0),
        "cpu_seconds": max(active_end.cpu_seconds - start.cpu_seconds, 0.0),
    }
