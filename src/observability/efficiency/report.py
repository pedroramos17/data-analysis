"""Efficiency report generation and quality gates."""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

from src.observability.efficiency.profiler import EfficiencyMetric
from src.security.secret_redaction import env_secret_values, redact_secrets


@dataclass(frozen=True, slots=True)
class EfficiencyGateConfig:
    """Quality gates for pipeline efficiency."""

    max_pipeline_minutes_local: float = 30.0
    max_peak_memory_mb: float = 4096.0
    min_rows_per_second: float = 10000.0
    max_gpu_job_minutes: float = 60.0
    max_cost_per_run_usd: float = 2.0

    @classmethod
    def from_config(cls, config: Mapping[str, object]) -> EfficiencyGateConfig:
        """Build gate config from an `efficiency_gates:` mapping."""
        gates = config.get("efficiency_gates") if isinstance(config.get("efficiency_gates"), Mapping) else {}
        return cls(
            max_pipeline_minutes_local=_float(gates.get("max_pipeline_minutes_local"), 30.0),
            max_peak_memory_mb=_float(gates.get("max_peak_memory_mb"), 4096.0),
            min_rows_per_second=_float(gates.get("min_rows_per_second"), 10000.0),
            max_gpu_job_minutes=_float(gates.get("max_gpu_job_minutes"), 60.0),
            max_cost_per_run_usd=_float(gates.get("max_cost_per_run_usd"), 2.0),
        )

    def to_dict(self) -> dict[str, float]:
        """Return a JSON-friendly gate config."""
        return {
            "max_pipeline_minutes_local": self.max_pipeline_minutes_local,
            "max_peak_memory_mb": self.max_peak_memory_mb,
            "min_rows_per_second": self.min_rows_per_second,
            "max_gpu_job_minutes": self.max_gpu_job_minutes,
            "max_cost_per_run_usd": self.max_cost_per_run_usd,
        }


def build_efficiency_report(
    run_id: int,
    metrics: Sequence[EfficiencyMetric | Mapping[str, object]],
    config: Mapping[str, object] | None = None,
) -> dict[str, object]:
    """Build an efficiency report payload."""
    metric_payloads = [_metric_payload(metric) for metric in metrics]
    gates = EfficiencyGateConfig.from_config(config or {})
    total_wall = sum(_float(metric.get("wall_clock_seconds"), 0.0) for metric in metric_payloads)
    total_cpu = sum(_float(metric.get("cpu_seconds"), 0.0) for metric in metric_payloads)
    total_rows = sum(_int(metric.get("rows_processed"), 0) for metric in metric_payloads)
    total_cost = sum(_float(metric.get("estimated_cloud_cost_usd"), 0.0) for metric in metric_payloads)
    peak_memory = max((_float(metric.get("peak_ram_mb"), 0.0) for metric in metric_payloads), default=0.0)
    rows_per_second = total_rows / total_wall if total_rows > 0 and total_wall > 0 else 0.0
    slowest = sorted(metric_payloads, key=lambda item: _float(item.get("wall_clock_seconds"), 0.0), reverse=True)[:5]
    summary = {
        "task_count": len(metric_payloads),
        "total_wall_clock_seconds": round(total_wall, 6),
        "total_cpu_seconds": round(total_cpu, 6),
        "peak_memory_mb": round(peak_memory, 6),
        "total_rows_processed": total_rows,
        "rows_per_second": round(rows_per_second, 6),
        "estimated_cloud_cost_usd": round(total_cost, 6),
        "cost_per_1m_rows_usd": _cost_per_1m_rows(total_cost, total_rows),
    }
    gate_results = _quality_gates(summary, metric_payloads, gates)
    report = {
        "pipeline_run_id": run_id,
        "summary": summary,
        "slowest_tasks": slowest,
        "metrics": metric_payloads,
        "quality_gates": gate_results,
        "quality_gates_passed": all(item["passed"] for item in gate_results.values()),
        "recommendations": _recommendations(summary, slowest, gate_results),
        "gate_config": gates.to_dict(),
    }
    return report


def write_efficiency_report(
    run_id: int,
    report: Mapping[str, object],
    report_root: str | Path = Path("reports") / "efficiency",
) -> dict[str, str]:
    """Write JSON and Markdown efficiency reports."""
    root = Path(report_root)
    root.mkdir(parents=True, exist_ok=True)
    json_path = root / f"pipeline_run_{run_id}.json"
    md_path = root / f"pipeline_run_{run_id}.md"
    safe_report = redact_secrets(report, env_secret_values())
    json_path.write_text(json.dumps(safe_report, sort_keys=True, indent=2, default=str), encoding="utf-8")
    md_path.write_text(_markdown_report(safe_report), encoding="utf-8")
    return {"json_path": json_path.as_posix(), "markdown_path": md_path.as_posix()}


def _quality_gates(
    summary: Mapping[str, object],
    metrics: Sequence[Mapping[str, object]],
    gates: EfficiencyGateConfig,
) -> dict[str, dict[str, object]]:
    pipeline_minutes = _float(summary.get("total_wall_clock_seconds"), 0.0) / 60.0
    peak_memory = _float(summary.get("peak_memory_mb"), 0.0)
    rows_per_second = _float(summary.get("rows_per_second"), 0.0)
    cost = _float(summary.get("estimated_cloud_cost_usd"), 0.0)
    gpu_minutes = max(
        (_float(metric.get("wall_clock_seconds"), 0.0) / 60.0 for metric in metrics if metric.get("gpu_available")),
        default=0.0,
    )
    rows_gate_passed = rows_per_second >= gates.min_rows_per_second if _int(summary.get("total_rows_processed"), 0) > 0 else True
    return {
        "max_pipeline_minutes_local": _gate(pipeline_minutes <= gates.max_pipeline_minutes_local, pipeline_minutes, gates.max_pipeline_minutes_local),
        "max_peak_memory_mb": _gate(peak_memory <= gates.max_peak_memory_mb, peak_memory, gates.max_peak_memory_mb),
        "min_rows_per_second": _gate(rows_gate_passed, rows_per_second, gates.min_rows_per_second),
        "max_gpu_job_minutes": _gate(gpu_minutes <= gates.max_gpu_job_minutes, gpu_minutes, gates.max_gpu_job_minutes),
        "max_cost_per_run_usd": _gate(cost <= gates.max_cost_per_run_usd, cost, gates.max_cost_per_run_usd),
    }


def _gate(passed: bool, actual: float, limit: float) -> dict[str, object]:
    return {"passed": bool(passed), "actual": round(actual, 6), "limit": limit}


def _recommendations(
    summary: Mapping[str, object],
    slowest: Sequence[Mapping[str, object]],
    gates: Mapping[str, Mapping[str, object]],
) -> list[str]:
    recommendations: list[str] = []
    if slowest:
        names = ", ".join(str(task.get("name")) for task in slowest[:3])
        recommendations.append(f"Optimize slowest tasks first: {names}.")
    if not gates["max_peak_memory_mb"]["passed"]:
        recommendations.append("Reduce peak RAM with chunked reads, narrower columns, or streaming transforms.")
    if not gates["min_rows_per_second"]["passed"]:
        recommendations.append("Increase rows/sec by pushing filters into DuckDB/Parquet scans and avoiding Python row loops.")
    if not gates["max_cost_per_run_usd"]["passed"]:
        recommendations.append("Lower cloud cost by batching small windows, using CPU for small jobs, or reducing GPU runtime.")
    if _float(summary.get("estimated_cloud_cost_usd"), 0.0) == 0.0:
        recommendations.append("No cloud cost recorded; local/offline execution remains within budget-first defaults.")
    return recommendations


def _markdown_report(report: Mapping[str, object]) -> str:
    summary = _mapping(report.get("summary"))
    gates = _mapping(report.get("quality_gates"))
    slowest = report.get("slowest_tasks") if isinstance(report.get("slowest_tasks"), list) else []
    recommendations = report.get("recommendations") if isinstance(report.get("recommendations"), list) else []
    lines = [
        f"# Efficiency Report: pipeline_run_{report.get('pipeline_run_id')}",
        "",
        "## Summary",
        f"- Task count: {summary.get('task_count', 0)}",
        f"- Wall-clock seconds: {summary.get('total_wall_clock_seconds', 0)}",
        f"- CPU seconds: {summary.get('total_cpu_seconds', 0)}",
        f"- Peak memory MB: {summary.get('peak_memory_mb', 0)}",
        f"- Rows/sec: {summary.get('rows_per_second', 0)}",
        f"- Estimated cloud cost USD: {summary.get('estimated_cloud_cost_usd', 0)}",
        "",
        "## Slowest Tasks",
    ]
    for task in slowest:
        task_payload = _mapping(task)
        lines.append(f"- {task_payload.get('name')}: {task_payload.get('wall_clock_seconds')}s")
    lines.extend(["", "## Quality Gates"])
    for name, gate in gates.items():
        gate_payload = _mapping(gate)
        status = "PASS" if gate_payload.get("passed") else "FAIL"
        lines.append(f"- {name}: {status} (actual={gate_payload.get('actual')}, limit={gate_payload.get('limit')})")
    lines.extend(["", "## Recommendations"])
    for recommendation in recommendations:
        lines.append(f"- {recommendation}")
    lines.append("")
    return "\n".join(lines)


def _metric_payload(metric: EfficiencyMetric | Mapping[str, object]) -> dict[str, object]:
    if isinstance(metric, EfficiencyMetric):
        return metric.to_dict()
    return dict(metric)


def _mapping(value: object) -> Mapping[str, object]:
    return value if isinstance(value, Mapping) else {}


def _float(value: object, default: float) -> float:
    if value in (None, ""):
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _int(value: object, default: int) -> int:
    if value in (None, ""):
        return default
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _cost_per_1m_rows(cost: float, rows: int) -> float:
    if cost <= 0 or rows <= 0:
        return 0.0
    return round(cost / (rows / 1_000_000.0), 6)
