"""Dataclasses shared by factor registry, execution, and evaluation."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd

from sourceflow.intelligence.symbolic.expression import FormulaExpression


@dataclass(frozen=True, slots=True)
class FactorDefinition:
    """A registered symbolic factor definition.

    Example:
        `FactorDefinition("coverage_intensity", "desc", expression)`
    """

    name: str
    description: str
    expression: FormulaExpression
    entity_type: str
    value_type: str = "numeric"
    status: str = "active"
    slug: str = ""
    source: str = "seed"
    max_depth: int = 0
    version: int = 1
    notes: str = ""

    @property
    def return_type(self) -> str:
        """Return the v2 return type alias.

        Example:
            `definition.return_type`
        """
        return self.value_type

    @property
    def object_level(self) -> str:
        """Return the v2 object level alias.

        Example:
            `definition.object_level`
        """
        return self.entity_type


@dataclass(frozen=True, slots=True)
class FactorDependency:
    """A dependency edge between two factor definitions.

    Example:
        `FactorDependency("risk", "claim_conflict", "factor")`
    """

    factor_name: str
    dependency_name: str
    dependency_type: str


@dataclass(frozen=True, slots=True)
class FactorExecutionPlan:
    """A compiled dataframe execution plan.

    Example:
        `plan.execute(frame)`
    """

    factor_name: str
    dependencies: tuple[str, ...]
    executor: object

    def execute(self, frame: pd.DataFrame) -> pd.Series:
        """Execute the compiled plan against a dataframe.

        Example:
            `values = plan.execute(frame)`
        """
        if not callable(self.executor):
            raise TypeError(f"Invalid executor {self.executor}; expected callable")
        return self.executor(frame)


@dataclass(frozen=True, slots=True)
class FactorRunRecord:
    """A recorded factor computation run.

    Example:
        `FactorRunRecord("coverage", "finished", 10, path)`
    """

    factor_name: str
    status: str
    row_count: int = 0
    output_parquet_path: Path | None = None
    error_message: str = ""
    run_started_at: str = ""
    run_finished_at: str = ""


@dataclass(frozen=True, slots=True)
class FactorScore:
    """A multi-objective factor evaluation score.

    Example:
        `FactorScore("coverage", "growth", 0.5, 0.8, 0.4, 2, 0.0)`
    """

    factor_name: str
    objective: str
    utility: float
    stability: float
    novelty: float
    complexity: int
    leakage: float
    metadata: MappingProxy = field(default_factory=dict)

    @property
    def score(self) -> float:
        """Return the default multi-objective score.

        Example:
            `score = factor_score.score`
        """
        return (
            self.utility
            + self.stability
            + self.novelty
            - self.complexity * 0.01
            - self.leakage
        )

    @property
    def final_score(self) -> float:
        """Return the canonical v2 final score alias.

        Example:
            `score.final_score`
        """
        return self.score


MappingProxy = dict[str, object]


@dataclass(frozen=True, slots=True)
class StoredFactorValues:
    """A Parquet factor value artifact.

    Example:
        `StoredFactorValues("coverage", path, 10)`
    """

    factor_name: str
    path: Path
    row_count: int


@dataclass(frozen=True, slots=True)
class FactorValueArtifact:
    """A SQLite registry row for a Parquet factor value artifact.

    Example:
        `artifact = registry.latest_factor_value_artifact("coverage_intensity")`
    """

    id: int
    factor_name: str
    as_of: str
    parquet_path: Path
    row_count: int
    created_at: str
    object_level: str = ""
    time_window_start: str = ""
    time_window_end: str = ""
    content_hash: str = ""


@dataclass(frozen=True, slots=True)
class FactorEvaluationRecord:
    """A SQLite registry row for a factor evaluation.

    Example:
        `records = registry.list_factor_evaluations(limit=10)`
    """

    id: int
    factor_name: str
    objective: str
    utility: float
    stability: float
    novelty: float
    complexity: int
    leakage: float
    score: float
    metadata: MappingProxy
    evaluated_at: str


@dataclass(frozen=True, slots=True)
class FactorRunRegistryRecord:
    """A SQLite row for a factor run.

    Example:
        `runs = registry.list_factor_runs("coverage")`
    """

    id: int
    factor_name: str
    run_started_at: str
    run_finished_at: str
    status: str
    row_count: int
    output_parquet_path: Path | None
    error_message: str


@dataclass(frozen=True, slots=True)
class FactorRegistrySummary:
    """Aggregate counts used by the intelligence operator UI.

    Example:
        `summary = registry.summary()`
    """

    factor_count: int
    artifact_count: int
    evaluation_count: int


def factor_names(definitions: Sequence[FactorDefinition]) -> tuple[str, ...]:
    """Return stable factor names from definitions.

    Example:
        `names = factor_names(definitions)`
    """
    return tuple(definition.name for definition in definitions)
