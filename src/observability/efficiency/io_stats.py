"""Process I/O statistics for efficiency profiling."""

from __future__ import annotations

import resource
from dataclasses import dataclass

from src.observability.efficiency.units import (
    BYTES_PER_MIB,
    DISK_BLOCK_BYTES,
    ROUND_DIGITS,
)


@dataclass(frozen=True, slots=True)
class IOSnapshot:
    """Process disk I/O snapshot."""

    read_bytes: int = 0
    write_bytes: int = 0
    block_reads: int = 0
    block_writes: int = 0


def io_snapshot() -> IOSnapshot:
    """Return process disk I/O counters."""
    proc = _proc_io()
    usage = resource.getrusage(resource.RUSAGE_SELF)
    return IOSnapshot(
        read_bytes=int(proc.get("read_bytes", 0)),
        write_bytes=int(proc.get("write_bytes", 0)),
        block_reads=int(getattr(usage, "ru_inblock", 0)),
        block_writes=int(getattr(usage, "ru_oublock", 0)),
    )


def io_delta(start: IOSnapshot, end: IOSnapshot | None = None) -> dict[str, float]:
    """Return disk read/write MB between snapshots."""
    active_end = end or io_snapshot()
    read_bytes = max(active_end.read_bytes - start.read_bytes, 0)
    write_bytes = max(active_end.write_bytes - start.write_bytes, 0)
    if read_bytes == 0:
        read_bytes = max(active_end.block_reads - start.block_reads, 0) * DISK_BLOCK_BYTES
    if write_bytes == 0:
        write_bytes = max(active_end.block_writes - start.block_writes, 0) * DISK_BLOCK_BYTES
    return {
        "disk_read_mb": round(read_bytes / BYTES_PER_MIB, ROUND_DIGITS),
        "disk_write_mb": round(write_bytes / BYTES_PER_MIB, ROUND_DIGITS),
    }


def _proc_io() -> dict[str, int]:
    try:
        with open("/proc/self/io", encoding="utf-8") as handle:
            rows = handle.read().splitlines()
    except OSError:
        return {}
    result: dict[str, int] = {}
    for row in rows:
        if ":" not in row:
            continue
        key, value = row.split(":", 1)
        try:
            result[key.strip()] = int(value.strip())
        except ValueError:
            continue
    return result
