"""Optional GPU statistics for efficiency profiling."""

from __future__ import annotations

import subprocess
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class GPUStats:
    """GPU utilization and memory snapshot."""

    available: bool = False
    utilization_percent: float = 0.0
    memory_used_mb: float = 0.0
    memory_total_mb: float = 0.0
    memory_peak_mb: float = 0.0
    provider: str = "none"

    def to_dict(self) -> dict[str, object]:
        """Return a JSON-friendly payload."""
        return {
            "available": self.available,
            "gpu_utilization_percent": self.utilization_percent,
            "gpu_memory_used_mb": self.memory_used_mb,
            "gpu_memory_total_mb": self.memory_total_mb,
            "gpu_memory_peak_mb": self.memory_peak_mb,
            "provider": self.provider,
        }


def gpu_snapshot() -> GPUStats:
    """Return GPU stats when `nvidia-smi` is available."""
    command = [
        "nvidia-smi",
        "--query-gpu=utilization.gpu,memory.used,memory.total",
        "--format=csv,noheader,nounits",
    ]
    try:
        result = subprocess.run(command, check=False, capture_output=True, text=True, timeout=2)
    except (OSError, subprocess.SubprocessError):
        return GPUStats()
    if result.returncode != 0 or not result.stdout.strip():
        return GPUStats()
    first = result.stdout.strip().splitlines()[0]
    parts = [part.strip() for part in first.split(",")]
    if len(parts) < 3:
        return GPUStats()
    try:
        utilization = float(parts[0])
        memory_used = float(parts[1])
        memory_total = float(parts[2])
    except ValueError:
        return GPUStats()
    return GPUStats(
        available=True,
        utilization_percent=utilization,
        memory_used_mb=memory_used,
        memory_total_mb=memory_total,
        memory_peak_mb=memory_used,
        provider="nvidia-smi",
    )


def gpu_delta(start: GPUStats, end: GPUStats | None = None) -> dict[str, object]:
    """Return GPU metrics across a profiling interval."""
    active_end = end or gpu_snapshot()
    return {
        "gpu_available": bool(start.available or active_end.available),
        "gpu_utilization_percent": max(start.utilization_percent, active_end.utilization_percent),
        "gpu_memory_peak_mb": max(start.memory_peak_mb, active_end.memory_peak_mb, active_end.memory_used_mb),
        "gpu_memory_total_mb": max(start.memory_total_mb, active_end.memory_total_mb),
        "gpu_provider": active_end.provider if active_end.available else start.provider,
    }
