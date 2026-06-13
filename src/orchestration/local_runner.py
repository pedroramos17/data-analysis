"""Local-first pipeline DAG runner."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from time import perf_counter

from src.observability.efficiency import build_efficiency_report, profile_task, write_efficiency_report
from src.orchestration.dag import PipelineDAG, dag_from_config
from src.orchestration.retries import RetryPolicy, retry_policy_from_config
from src.orchestration.state import PipelineRunRecord, PipelineStateStore, PipelineTaskRecord
from src.orchestration.tasks import TaskContext, TaskHandler, default_task_handlers
from src.providers.registry import ProviderRegistry


@dataclass(frozen=True, slots=True)
class PipelineRunResult:
    """Result from running or resuming a pipeline DAG."""

    run: PipelineRunRecord
    tasks: tuple[PipelineTaskRecord, ...]
    artifacts: dict[str, str] = field(default_factory=dict)
    graph: dict[str, object] = field(default_factory=dict)

    def to_dict(self) -> dict[str, object]:
        """Return a JSON-friendly payload."""
        return {
            "run": self.run.to_dict(),
            "tasks": [task.to_dict() for task in self.tasks],
            "artifacts": dict(self.artifacts),
            "graph": dict(self.graph),
        }


@dataclass(slots=True)
class LocalPipelineRunner:
    """Execute a pipeline DAG in the local process."""

    registry: ProviderRegistry
    state: PipelineStateStore | None = None
    handlers: dict[str, TaskHandler] = field(default_factory=default_task_handlers)

    def __post_init__(self) -> None:
        if self.state is None:
            self.state = PipelineStateStore.from_settings(self.registry.settings)

    def dry_run(self, config: Mapping[str, object]) -> dict[str, object]:
        """Return a graph plan without writing run/task state."""
        dag = dag_from_config(config)
        return {
            "status": "DRY_RUN",
            "name": _pipeline_name(config),
            "graph": dag.to_dict(),
            "cost_estimate": _cost_estimate(config),
        }

    def run(self, config: Mapping[str, object]) -> PipelineRunResult:
        """Create and execute a new pipeline run."""
        run = self.state.create_run(  # type: ignore[union-attr]
            _pipeline_name(config),
            dict(config),
            cost_estimate=_cost_estimate(config),
        )
        return self._execute(run, dag_from_config(config), dict(config))

    def resume(self, run_id: int) -> PipelineRunResult:
        """Resume an existing failed or partial pipeline run."""
        run = self.state.mark_run_running(run_id)  # type: ignore[union-attr]
        config = dict(run.config_json)
        return self._execute(run, dag_from_config(config), config)

    def status(self, run_id: int) -> dict[str, object]:
        """Return persisted pipeline status."""
        return self.state.status_payload(run_id)  # type: ignore[union-attr]

    def _execute(
        self,
        run: PipelineRunRecord,
        dag: PipelineDAG,
        config: Mapping[str, object],
    ) -> PipelineRunResult:
        artifacts: dict[str, str] = self._completed_artifacts(run.id)
        retry_policy = retry_policy_from_config(config)
        started = perf_counter()
        try:
            for node in dag.topological_nodes():
                input_hash = _input_hash(node.name, config, artifacts)
                existing = self.state.get_task(run.id, node.name)  # type: ignore[union-attr]
                if existing and existing.status in {"COMPLETED", "SKIPPED"} and existing.input_hash == input_hash:
                    if existing.output_uri:
                        artifacts[node.name] = existing.output_uri
                    continue
                task_record = self._run_task_with_retries(
                    run,
                    node.name,
                    input_hash,
                    dict(config),
                    dict(artifacts),
                    retry_policy,
                )
                if task_record.output_uri:
                    artifacts[node.name] = task_record.output_uri
            tasks = self.state.list_tasks(run.id)  # type: ignore[union-attr]
            efficiency = self._efficiency_payload(
                run.id,
                config,
                tasks,
                round(perf_counter() - started, 6),
            )
            final_run = self.state.update_run_status(run.id, "COMPLETED", efficiency=efficiency)  # type: ignore[union-attr]
            return PipelineRunResult(final_run, self.state.list_tasks(run.id), artifacts, dag.to_dict())  # type: ignore[union-attr]
        except Exception as exc:
            error = {"type": type(exc).__name__, "message": str(exc)}
            failed_run = self.state.update_run_status(run.id, "FAILED", error=error)  # type: ignore[union-attr]
            return PipelineRunResult(failed_run, self.state.list_tasks(run.id), artifacts, dag.to_dict())  # type: ignore[union-attr]

    def _run_task_with_retries(
        self,
        run: PipelineRunRecord,
        task_name: str,
        input_hash: str,
        config: dict[str, object],
        artifacts: dict[str, str],
        retry_policy: RetryPolicy,
    ) -> PipelineTaskRecord:
        handler = self.handlers.get(task_name)
        if handler is None:
            raise ValueError(f"No handler registered for pipeline task {task_name!r}")
        attempt = 0
        while True:
            attempt += 1
            retry_count = attempt - 1
            self.state.start_task(run.id, task_name, input_hash, retry_count=retry_count)  # type: ignore[union-attr]
            try:
                profiler = profile_task(task_name, pipeline_run_id=run.id, runner="local")
                with profiler:
                    result = handler(
                        TaskContext(
                            run.id,
                            run.name,
                            task_name,
                            config,
                            artifacts,
                            self.registry,
                        )
                    )
                    profiler.observe_result(result.to_dict())
            except Exception as exc:
                error = {"type": type(exc).__name__, "message": str(exc)}
                self.state.fail_task(run.id, task_name, input_hash, error, retry_count=retry_count)  # type: ignore[union-attr]
                if retry_policy.should_retry(attempt):
                    retry_policy.sleep_before_retry(attempt)
                    continue
                raise
            return self.state.complete_task(  # type: ignore[union-attr]
                run.id,
                task_name,
                input_hash,
                result.output_uri,
                metadata=result.metadata
                | {"artifacts": result.artifacts, "efficiency": _metric_dict(profiler.metric)},
                retry_count=retry_count,
                status=result.status,
            )

    def _completed_artifacts(self, run_id: int) -> dict[str, str]:
        artifacts: dict[str, str] = {}
        for task in self.state.list_tasks(run_id):  # type: ignore[union-attr]
            if task.status in {"COMPLETED", "SKIPPED"} and task.output_uri:
                artifacts[task.task_name] = task.output_uri
        return artifacts

    def _efficiency_payload(
        self,
        run_id: int,
        config: Mapping[str, object],
        tasks: tuple[PipelineTaskRecord, ...],
        duration_seconds: float,
    ) -> dict[str, object]:
        metrics = [task.metadata_json.get("efficiency", {}) for task in tasks if task.metadata_json.get("efficiency")]
        report = build_efficiency_report(run_id, metrics, _efficiency_config(self.registry.settings, config))
        paths = write_efficiency_report(run_id, report, self.registry.settings.efficiency.report_root)
        self._append_efficiency_jsonl(run_id, metrics)
        return {
            "duration_seconds": duration_seconds,
            "runner": "local",
            "report": report,
            "report_paths": paths,
        }

    def _append_efficiency_jsonl(self, run_id: int, metrics: list[object]) -> None:
        output_path = Path(self.registry.settings.efficiency.output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with output_path.open("a", encoding="utf-8") as handle:
            for metric in metrics:
                handle.write(json.dumps({"pipeline_run_id": run_id, "metric": metric}, sort_keys=True, default=str) + "\n")


def _pipeline_name(config: Mapping[str, object]) -> str:
    pipeline = config.get("pipeline") if isinstance(config.get("pipeline"), Mapping) else config
    if isinstance(pipeline, Mapping):
        return str(pipeline.get("name") or config.get("name") or "pipeline_mvp")
    return str(config.get("name") or "pipeline_mvp")


def _cost_estimate(config: Mapping[str, object]) -> dict[str, object]:
    value = config.get("cost_estimate")
    if isinstance(value, Mapping):
        return dict(value)
    return {"estimated_cost_usd": 0.0, "currency": "USD", "provider": "local"}


def _input_hash(task_name: str, config: Mapping[str, object], artifacts: Mapping[str, str]) -> str:
    payload = {
        "task_name": task_name,
        "config": _task_relevant_config(task_name, config),
        "artifacts": dict(sorted(artifacts.items())),
    }
    encoded = json.dumps(payload, sort_keys=True, default=str).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _task_relevant_config(task_name: str, config: Mapping[str, object]) -> object:
    keys = {task_name, "task_configs", "pipeline", "retries"}
    return {key: value for key, value in config.items() if key in keys}


def _metric_dict(metric: object) -> dict[str, object]:
    to_dict = getattr(metric, "to_dict", None)
    if callable(to_dict):
        payload = to_dict()
        if isinstance(payload, Mapping):
            return dict(payload)
    return {}


def _efficiency_config(settings: object, config: Mapping[str, object]) -> dict[str, object]:
    if isinstance(config.get("efficiency_gates"), Mapping):
        return dict(config)
    efficiency = getattr(settings, "efficiency")
    return {
        **dict(config),
        "efficiency_gates": {
            "max_pipeline_minutes_local": efficiency.max_pipeline_minutes_local,
            "max_peak_memory_mb": efficiency.max_peak_memory_mb,
            "min_rows_per_second": efficiency.min_rows_per_second,
            "max_gpu_job_minutes": efficiency.max_gpu_job_minutes,
            "max_cost_per_run_usd": efficiency.max_cost_per_run_usd,
        },
    }
