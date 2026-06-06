"""Pipeline DAG definitions for local-first orchestration."""

from __future__ import annotations

from collections import defaultdict, deque
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field

PIPELINE_TASK_ORDER = (
    "ingest_raw",
    "preprocess",
    "extract_features",
    "build_sliding_windows",
    "train_baselines",
    "train_neural_optional",
    "predict",
    "evaluate",
    "backtest",
    "risk_report",
    "aggregate_report",
)


@dataclass(frozen=True, slots=True)
class PipelineTaskNode:
    """One DAG task node."""

    name: str
    depends_on: tuple[str, ...] = ()
    optional: bool = False


@dataclass(frozen=True, slots=True)
class PipelineDAG:
    """Directed acyclic graph for pipeline task execution."""

    nodes: tuple[PipelineTaskNode, ...]
    metadata: dict[str, object] = field(default_factory=dict)

    def task_names(self) -> tuple[str, ...]:
        """Return task names in topological order."""
        return tuple(node.name for node in self.topological_nodes())

    def topological_nodes(self) -> tuple[PipelineTaskNode, ...]:
        """Return nodes in dependency order."""
        by_name = {node.name: node for node in self.nodes}
        indegree: dict[str, int] = {node.name: 0 for node in self.nodes}
        children: dict[str, list[str]] = defaultdict(list)
        for node in self.nodes:
            for dependency in node.depends_on:
                if dependency not in by_name:
                    raise ValueError(f"Unknown dependency {dependency!r} for task {node.name!r}")
                indegree[node.name] += 1
                children[dependency].append(node.name)
        queue = deque(name for name, degree in indegree.items() if degree == 0)
        ordered: list[PipelineTaskNode] = []
        while queue:
            name = queue.popleft()
            ordered.append(by_name[name])
            for child in children[name]:
                indegree[child] -= 1
                if indegree[child] == 0:
                    queue.append(child)
        if len(ordered) != len(self.nodes):
            raise ValueError("Pipeline DAG contains a cycle")
        return tuple(ordered)

    def edges(self) -> tuple[tuple[str, str], ...]:
        """Return graph edges as `(dependency, task)` pairs."""
        return tuple((dependency, node.name) for node in self.nodes for dependency in node.depends_on)

    def to_dict(self) -> dict[str, object]:
        """Return a JSON-friendly DAG payload."""
        return {
            "tasks": [
                {"name": node.name, "depends_on": list(node.depends_on), "optional": node.optional}
                for node in self.topological_nodes()
            ],
            "edges": [list(edge) for edge in self.edges()],
            "metadata": dict(self.metadata),
        }


def default_pipeline_dag(enabled_tasks: Iterable[str] | None = None) -> PipelineDAG:
    """Build the default MVP pipeline DAG."""
    enabled = tuple(enabled_tasks or PIPELINE_TASK_ORDER)
    unknown = set(enabled).difference(PIPELINE_TASK_ORDER)
    if unknown:
        raise ValueError(f"Unknown pipeline tasks: {sorted(unknown)!r}")
    nodes: list[PipelineTaskNode] = []
    previous = ""
    for task_name in PIPELINE_TASK_ORDER:
        if task_name not in enabled:
            continue
        depends_on = (previous,) if previous else ()
        nodes.append(
            PipelineTaskNode(
                task_name,
                depends_on,
                optional=task_name == "train_neural_optional",
            )
        )
        previous = task_name
    return PipelineDAG(tuple(nodes), {"name": "default_mvp"})


def dag_from_config(config: Mapping[str, object]) -> PipelineDAG:
    """Build a pipeline DAG from config or return the default DAG."""
    pipeline = config.get("pipeline") if isinstance(config.get("pipeline"), Mapping) else config
    tasks = pipeline.get("tasks") if isinstance(pipeline, Mapping) else None
    if isinstance(tasks, list) and tasks:
        return default_pipeline_dag(str(task) for task in tasks)
    return default_pipeline_dag()
