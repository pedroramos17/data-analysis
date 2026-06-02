"""NetworkX DAG construction and scheduling for factor computation."""

from __future__ import annotations

import networkx as nx
from django.db import connection as django_connection
from django.utils import timezone

from sourceflow.intelligence.factor_base.dependencies import expression_dependencies
from sourceflow.intelligence.factor_base.registry import FactorRegistry
from sourceflow.intelligence.factor_base.types import FactorDefinition, FactorRunRecord
from sourceflow.intelligence.symbolic.compiler import (
    FactorExecutionContext,
    execute_factor,
)


def build_factor_dag(definitions: tuple[FactorDefinition, ...]) -> nx.DiGraph:
    """Build a directed factor dependency graph.

    Example:
        `graph = build_factor_dag(seed_factor_definitions())`
    """
    graph = nx.DiGraph()
    names = {definition.name for definition in definitions}
    for definition in definitions:
        graph.add_node(definition.name, definition=definition)
        _add_dependency_edges(graph, definition, names)
    return graph


def schedule_factor_computation(
    definitions: tuple[FactorDefinition, ...],
) -> tuple[FactorDefinition, ...]:
    """Return factors in dependency-safe computation order.

    Example:
        `ordered = schedule_factor_computation(definitions)`
    """
    graph = build_factor_dag(definitions)
    if not nx.is_directed_acyclic_graph(graph):
        raise ValueError("Invalid factor dependency graph; expected acyclic graph")
    by_name = {definition.name: definition for definition in definitions}
    return tuple(
        by_name[name] for name in nx.topological_sort(graph) if name in by_name
    )


def execute_factor_dag(
    definitions: tuple[FactorDefinition, ...],
    context: FactorExecutionContext,
    force: bool = False,
) -> tuple[object, ...]:
    """Execute factors in dependency-safe order and materialize Parquet values.

    Example:
        `paths = execute_factor_dag(definitions, context, force=True)`
    """
    executed: list[object] = []
    registry = _registry(context)
    for definition in schedule_factor_computation(definitions):
        path = _execute_one_factor(definition, context, registry, force)
        if path is not None:
            executed.append(path)
    return tuple(executed)


def _add_dependency_edges(
    graph: nx.DiGraph,
    definition: FactorDefinition,
    known_names: set[str],
) -> None:
    for dependency in expression_dependencies(definition.expression):
        if dependency in known_names:
            graph.add_edge(dependency, definition.name)


def _execute_one_factor(
    definition: FactorDefinition,
    context: FactorExecutionContext,
    registry: FactorRegistry,
    force: bool,
) -> object | None:
    storage = _storage(context)
    if not force and storage.latest_path(definition.name) is not None:
        return None
    started_at = timezone.now().isoformat()
    try:
        rows = execute_factor(definition, context)
        path = storage.write_values(definition.name, rows)
        _record_success(registry, definition, context, path, rows, started_at)
        return path
    except Exception as error:
        _record_failure(registry, definition, started_at, error)
        raise


def _record_success(
    registry: FactorRegistry,
    definition: FactorDefinition,
    context: FactorExecutionContext,
    path: object,
    rows: list[dict[str, object]],
    started_at: str,
) -> None:
    finished_at = timezone.now().isoformat()
    registry.record_factor_values(
        definition.name,
        context.as_of,
        path,
        len(rows),
        object_level=definition.entity_type,
        time_window_start=context.history_start,
        time_window_end=context.history_end,
    )
    registry.record_factor_run(
        FactorRunRecord(
            definition.name, "finished", len(rows), path, "", started_at, finished_at
        )
    )


def _record_failure(
    registry: FactorRegistry,
    definition: FactorDefinition,
    started_at: str,
    error: Exception,
) -> None:
    registry.record_factor_run(
        FactorRunRecord(
            definition.name,
            "failed",
            error_message=str(error),
            run_started_at=started_at,
            run_finished_at=timezone.now().isoformat(),
        )
    )


def _registry(context: FactorExecutionContext) -> FactorRegistry:
    return FactorRegistry(context.connection or django_connection)


def _storage(context: FactorExecutionContext) -> object:
    if context.factor_storage is None:
        raise RuntimeError("Missing factor storage; expected FactorValueStorage")
    return context.factor_storage
