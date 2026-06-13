"""Efficiency profiler decorators and context managers."""

from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass, field
from functools import wraps
from types import TracebackType
from typing import Any, ParamSpec, TypeVar

from src.observability.efficiency.gpu_stats import GPUStats, gpu_delta, gpu_snapshot
from src.observability.efficiency.io_stats import IOSnapshot, io_delta, io_snapshot
from src.observability.efficiency.memory import (
    MemorySnapshot,
    memory_delta,
    memory_snapshot,
    pandas_memory_usage_mb,
    start_memory_trace,
)
from src.observability.efficiency.timing import TimingSnapshot, timing_delta, timing_snapshot
from src.observability.efficiency.units import (
    PERCENTILE_SCALE,
    ROUND_DIGITS,
    ROWS_PER_MILLION,
)

P = ParamSpec("P")
R = TypeVar("R")


@dataclass(frozen=True, slots=True)
class EfficiencyMetric:
    """One profiled task/query/training-loop metric payload."""

    name: str
    category: str
    status: str
    wall_clock_seconds: float
    cpu_seconds: float
    peak_ram_mb: float
    disk_read_mb: float
    disk_write_mb: float
    parquet_rows_per_second: float = 0.0
    duckdb_query_seconds: float = 0.0
    pandas_memory_usage_mb: float = 0.0
    training_samples_per_second: float = 0.0
    inference_latency_p50_ms: float = 0.0
    inference_latency_p95_ms: float = 0.0
    inference_latency_p99_ms: float = 0.0
    gpu_available: bool = False
    gpu_utilization_percent: float = 0.0
    gpu_memory_peak_mb: float = 0.0
    estimated_cloud_cost_usd: float = 0.0
    cost_per_training_window_usd: float = 0.0
    cost_per_1m_rows_usd: float = 0.0
    cost_per_model_candidate_usd: float = 0.0
    rows_processed: int = 0
    training_samples: int = 0
    training_windows: int = 0
    model_candidates: int = 0
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, object]:
        """Return a JSON-friendly metric payload."""
        return {
            "name": self.name,
            "category": self.category,
            "status": self.status,
            "wall_clock_seconds": self.wall_clock_seconds,
            "cpu_seconds": self.cpu_seconds,
            "peak_ram_mb": self.peak_ram_mb,
            "disk_read_mb": self.disk_read_mb,
            "disk_write_mb": self.disk_write_mb,
            "parquet_rows_per_second": self.parquet_rows_per_second,
            "duckdb_query_seconds": self.duckdb_query_seconds,
            "pandas_memory_usage_mb": self.pandas_memory_usage_mb,
            "training_samples_per_second": self.training_samples_per_second,
            "inference_latency_p50_ms": self.inference_latency_p50_ms,
            "inference_latency_p95_ms": self.inference_latency_p95_ms,
            "inference_latency_p99_ms": self.inference_latency_p99_ms,
            "gpu_available": self.gpu_available,
            "gpu_utilization_percent": self.gpu_utilization_percent,
            "gpu_memory_peak_mb": self.gpu_memory_peak_mb,
            "estimated_cloud_cost_usd": self.estimated_cloud_cost_usd,
            "cost_per_training_window_usd": self.cost_per_training_window_usd,
            "cost_per_1m_rows_usd": self.cost_per_1m_rows_usd,
            "cost_per_model_candidate_usd": self.cost_per_model_candidate_usd,
            "rows_processed": self.rows_processed,
            "training_samples": self.training_samples,
            "training_windows": self.training_windows,
            "model_candidates": self.model_candidates,
            "metadata": dict(self.metadata),
        }


@dataclass(slots=True)
class EfficiencyProfiler:
    """Decorator/context manager for task-level efficiency metrics."""

    name: str
    category: str = "task"
    metadata: dict[str, Any] = field(default_factory=dict)
    rows_processed: int = 0
    parquet_rows: int = 0
    duckdb_query_seconds: float = 0.0
    training_samples: int = 0
    training_windows: int = 0
    model_candidates: int = 0
    inference_latencies_ms: list[float] = field(default_factory=list)
    estimated_cloud_cost_usd: float = 0.0
    pandas_memory_usage_mb: float = 0.0
    metric: EfficiencyMetric | None = None
    _timing_start: TimingSnapshot | None = field(default=None, init=False)
    _memory_start: MemorySnapshot | None = field(default=None, init=False)
    _io_start: IOSnapshot | None = field(default=None, init=False)
    _gpu_start: GPUStats | None = field(default=None, init=False)

    def __call__(self, func: Callable[P, R]) -> Callable[P, R]:
        """Use this profiler as a decorator."""
        @wraps(func)
        def wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
            with self:
                result = func(*args, **kwargs)
                self.observe_result(result)
                return result

        return wrapper

    def __enter__(self) -> EfficiencyProfiler:
        """Start profiling."""
        start_memory_trace()
        self._timing_start = timing_snapshot()
        self._memory_start = memory_snapshot()
        self._io_start = io_snapshot()
        self._gpu_start = gpu_snapshot()
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> bool:
        """Stop profiling and record a metric."""
        self.metric = self._build_metric("FAILED" if exc_type else "COMPLETED")
        return False

    def observe_result(self, result: object) -> None:
        """Extract common row/sample counters from a task result."""
        payload = _as_mapping(result)
        self.rows_processed = max(self.rows_processed, _extract_int(payload, "rows", "row_count", "rows_written"))
        self.parquet_rows = max(self.parquet_rows, _extract_int(payload, "parquet_rows", "row_count", "rows"))
        self.training_samples = max(self.training_samples, _extract_int(payload, "training_samples", "samples", "rows"))
        self.training_windows = max(self.training_windows, _extract_int(payload, "training_windows", "window_count"))
        self.model_candidates = max(self.model_candidates, _extract_int(payload, "model_candidates", "candidate_count"))
        self.estimated_cloud_cost_usd = max(
            self.estimated_cloud_cost_usd,
            _extract_float(payload, "estimated_cloud_cost_usd", "estimated_cost_usd", "gpu_hourly_cost"),
        )
        self.pandas_memory_usage_mb = max(self.pandas_memory_usage_mb, pandas_memory_usage_mb(result))
        latencies = payload.get("inference_latencies_ms")
        if isinstance(latencies, Iterable) and not isinstance(latencies, str | bytes):
            self.inference_latencies_ms.extend(float(value) for value in latencies)

    def add_inference_latency_ms(self, latency_ms: float) -> None:
        """Record one inference latency sample."""
        self.inference_latencies_ms.append(float(latency_ms))

    def _build_metric(self, status: str) -> EfficiencyMetric:
        timing = timing_delta(self._timing_start or timing_snapshot())
        memory = memory_delta(self._memory_start or memory_snapshot())
        io = io_delta(self._io_start or io_snapshot())
        gpu = gpu_delta(self._gpu_start or gpu_snapshot())
        wall_seconds = timing["wall_clock_seconds"]
        rows = max(self.rows_processed, self.parquet_rows)
        return EfficiencyMetric(
            name=self.name,
            category=self.category,
            status=status,
            wall_clock_seconds=round(wall_seconds, ROUND_DIGITS),
            cpu_seconds=round(timing["cpu_seconds"], ROUND_DIGITS),
            peak_ram_mb=round(memory["peak_ram_mb"], ROUND_DIGITS),
            disk_read_mb=round(io["disk_read_mb"], ROUND_DIGITS),
            disk_write_mb=round(io["disk_write_mb"], ROUND_DIGITS),
            parquet_rows_per_second=_rate(self.parquet_rows, wall_seconds),
            duckdb_query_seconds=round(
                self.duckdb_query_seconds
                or (wall_seconds if self.category == "duckdb_query" else 0.0),
                ROUND_DIGITS,
            ),
            pandas_memory_usage_mb=round(self.pandas_memory_usage_mb, ROUND_DIGITS),
            training_samples_per_second=_rate(self.training_samples, wall_seconds),
            inference_latency_p50_ms=_percentile(self.inference_latencies_ms, 50),
            inference_latency_p95_ms=_percentile(self.inference_latencies_ms, 95),
            inference_latency_p99_ms=_percentile(self.inference_latencies_ms, 99),
            gpu_available=bool(gpu["gpu_available"]),
            gpu_utilization_percent=float(gpu["gpu_utilization_percent"]),
            gpu_memory_peak_mb=float(gpu["gpu_memory_peak_mb"]),
            estimated_cloud_cost_usd=round(self.estimated_cloud_cost_usd, ROUND_DIGITS),
            cost_per_training_window_usd=_cost_rate(self.estimated_cloud_cost_usd, self.training_windows),
            cost_per_1m_rows_usd=_cost_per_1m_rows(self.estimated_cloud_cost_usd, rows),
            cost_per_model_candidate_usd=_cost_rate(self.estimated_cloud_cost_usd, self.model_candidates),
            rows_processed=rows,
            training_samples=self.training_samples,
            training_windows=self.training_windows,
            model_candidates=self.model_candidates,
            metadata={**self.metadata, "gpu_provider": gpu.get("gpu_provider", "none")},
        )


def profile_task(name: str, **metadata: Any) -> EfficiencyProfiler:
    """Profile an arbitrary pipeline task."""
    return EfficiencyProfiler(name=name, category="task", metadata=dict(metadata))


def profile_duckdb_query(name: str, **metadata: Any) -> EfficiencyProfiler:
    """Profile a DuckDB query block or function."""
    return EfficiencyProfiler(name=name, category="duckdb_query", metadata=dict(metadata))


def profile_training_loop(name: str, **metadata: Any) -> EfficiencyProfiler:
    """Profile a model training loop."""
    return EfficiencyProfiler(name=name, category="training_loop", metadata=dict(metadata))


def _as_mapping(value: object) -> Mapping[str, object]:
    if isinstance(value, Mapping):
        return value
    to_dict = getattr(value, "to_dict", None)
    if callable(to_dict):
        converted = to_dict()
        if isinstance(converted, Mapping):
            return converted
    if hasattr(value, "__dict__"):
        return vars(value)
    return {}


def _extract_int(payload: Mapping[str, object], *keys: str) -> int:
    for key in keys:
        value = payload.get(key)
        if value not in (None, ""):
            try:
                return int(value)
            except (TypeError, ValueError):
                continue
    return 0


def _extract_float(payload: Mapping[str, object], *keys: str) -> float:
    for key in keys:
        value = payload.get(key)
        if value not in (None, ""):
            try:
                return float(value)
            except (TypeError, ValueError):
                continue
    return 0.0


def _rate(count: int, seconds: float) -> float:
    if count <= 0 or seconds <= 0:
        return 0.0
    return round(count / seconds, ROUND_DIGITS)


def _cost_rate(cost: float, denominator: int) -> float:
    if cost <= 0 or denominator <= 0:
        return 0.0
    return round(cost / denominator, ROUND_DIGITS)


def _cost_per_1m_rows(cost: float, rows: int) -> float:
    if cost <= 0 or rows <= 0:
        return 0.0
    return round(cost / (rows / ROWS_PER_MILLION), ROUND_DIGITS)


def _percentile(values: list[float], percentile: int) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    if len(ordered) == 1:
        return round(ordered[0], ROUND_DIGITS)
    position = (len(ordered) - 1) * (percentile / PERCENTILE_SCALE)
    lower = int(position)
    upper = min(lower + 1, len(ordered) - 1)
    weight = position - lower
    return round(ordered[lower] * (1 - weight) + ordered[upper] * weight, ROUND_DIGITS)
