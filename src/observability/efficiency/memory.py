"""Memory helpers for efficiency profiling."""

from __future__ import annotations

import os
import resource
import tracemalloc
from dataclasses import dataclass
from typing import Any

from src.observability.efficiency.units import (
    BYTES_PER_KIB,
    BYTES_PER_MIB,
    ROUND_DIGITS,
)


@dataclass(frozen=True, slots=True)
class MemorySnapshot:
    """Process memory snapshot."""

    rss_mb: float
    peak_rss_mb: float
    tracemalloc_current_mb: float = 0.0
    tracemalloc_peak_mb: float = 0.0


def memory_snapshot() -> MemorySnapshot:
    """Return current process memory counters."""
    current = peak = 0
    if tracemalloc.is_tracing():
        current, peak = tracemalloc.get_traced_memory()
    return MemorySnapshot(
        rss_mb=_current_rss_mb(),
        peak_rss_mb=_peak_rss_mb(),
        tracemalloc_current_mb=_bytes_to_mb(current),
        tracemalloc_peak_mb=_bytes_to_mb(peak),
    )


def start_memory_trace() -> None:
    """Start Python allocation tracing when not already active."""
    if not tracemalloc.is_tracing():
        tracemalloc.start()


def memory_delta(start: MemorySnapshot, end: MemorySnapshot | None = None) -> dict[str, float]:
    """Return memory metrics between two snapshots."""
    active_end = end or memory_snapshot()
    return {
        "rss_mb": active_end.rss_mb,
        "peak_ram_mb": max(active_end.peak_rss_mb, start.peak_rss_mb),
        "python_allocated_mb": active_end.tracemalloc_current_mb,
        "python_peak_allocated_mb": max(active_end.tracemalloc_peak_mb, start.tracemalloc_peak_mb),
    }


def pandas_memory_usage_mb(value: Any) -> float:
    """Return pandas object memory usage when a pandas-like object is supplied."""
    memory_usage = getattr(value, "memory_usage", None)
    if not callable(memory_usage):
        return 0.0
    try:
        usage = memory_usage(deep=True)
    except TypeError:
        usage = memory_usage()
    total = usage.sum() if hasattr(usage, "sum") else usage
    try:
        return _bytes_to_mb(float(total))
    except (TypeError, ValueError):
        return 0.0


def _current_rss_mb() -> float:
    statm = "/proc/self/statm"
    try:
        with open(statm, encoding="utf-8") as handle:
            parts = handle.read().split()
        pages = int(parts[1]) if len(parts) > 1 else 0
        return _bytes_to_mb(pages * os.sysconf("SC_PAGE_SIZE"))
    except (OSError, ValueError, IndexError):
        return _peak_rss_mb()


def _peak_rss_mb() -> float:
    usage = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    if os.name == "posix":
        return usage / BYTES_PER_KIB
    return _bytes_to_mb(float(usage))


def _bytes_to_mb(value: float) -> float:
    return round(value / BYTES_PER_MIB, ROUND_DIGITS)
