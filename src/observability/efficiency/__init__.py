"""Efficiency profiling, reports, and quality gates."""

from src.observability.efficiency.profiler import (
    EfficiencyMetric,
    EfficiencyProfiler,
    profile_duckdb_query,
    profile_task,
    profile_training_loop,
)
from src.observability.efficiency.report import (
    EfficiencyGateConfig,
    build_efficiency_report,
    write_efficiency_report,
)

__all__ = [
    "EfficiencyGateConfig",
    "EfficiencyMetric",
    "EfficiencyProfiler",
    "build_efficiency_report",
    "profile_duckdb_query",
    "profile_task",
    "profile_training_loop",
    "write_efficiency_report",
]
