"""Raw-SQL SQLite registry for symbolic factors."""

from __future__ import annotations

import json
from collections.abc import Sequence
from importlib import resources
from pathlib import Path

from sourceflow.intelligence.factor_base.dependencies import factor_dependencies
from sourceflow.intelligence.factor_base.types import (
    FactorDefinition,
    FactorEvaluationRecord,
    FactorRegistrySummary,
    FactorRunRecord,
    FactorRunRegistryRecord,
    FactorScore,
    FactorValueArtifact,
)
from sourceflow.intelligence.symbolic.expression import (
    expression_from_dict,
    expression_to_dict,
    formula_text,
    operator_count,
)


class FactorRegistry:
    """SQLite-backed registry for formulas and artifacts.

    Example:
        `registry = FactorRegistry(connection)`
    """

    def __init__(self, connection: object) -> None:
        """Store a DB connection compatible with Django cursors.

        Example:
            `FactorRegistry(django_connection)`
        """
        self.connection = connection

    def ensure_schema(self) -> None:
        """Create factor registry tables when absent.

        Example:
            `registry.ensure_schema()`
        """
        ensure_factor_schema(self.connection)

    def register_factor(self, definition: FactorDefinition) -> bool:
        """Upsert one factor definition and its dependencies.

        Example:
            `registry.register_factor(definition)`
        """
        self.ensure_schema()
        created = self.get_factor(definition.name, missing_ok=True) is None
        _upsert_factor(self.connection, definition)
        _replace_dependencies(self.connection, definition)
        return created

    def register_factors(self, definitions: Sequence[FactorDefinition]) -> int:
        """Register many factors and return the count processed.

        Example:
            `registry.register_factors(seed_factor_definitions())`
        """
        count = 0
        for definition in definitions:
            self.register_factor(definition)
            count += 1
        return count

    def get_factor(
        self, name: str, missing_ok: bool = False
    ) -> FactorDefinition | None:
        """Fetch one factor definition by name.

        Example:
            `factor = registry.get_factor("coverage_intensity")`
        """
        self.ensure_schema()
        row = _fetch_one(
            self.connection, "SELECT * FROM factors WHERE name = %s", [name]
        )
        if row is None and missing_ok:
            return None
        if row is None:
            raise KeyError(f"Missing factor {name}; expected registered factor")
        return _definition_from_row(row)

    def list_factors(
        self,
        status: str | None = "active",
        source: str = "",
    ) -> tuple[FactorDefinition, ...]:
        """List registered factors by status.

        Example:
            `factors = registry.list_factors()`
        """
        self.ensure_schema()
        rows = _factor_rows_by_status(self.connection, status, source)
        return tuple(_definition_from_row(row) for row in rows)

    def summary(self) -> FactorRegistrySummary:
        """Return factor, artifact, and evaluation counts.

        Example:
            `summary = registry.summary()`
        """
        self.ensure_schema()
        return FactorRegistrySummary(
            factor_count=_table_count(self.connection, "factors"),
            artifact_count=_table_count(self.connection, "factor_values"),
            evaluation_count=_table_count(self.connection, "factor_evaluations"),
        )

    def factor_dependencies(self, name: str) -> tuple[str, ...]:
        """List stored factor dependencies by factor name.

        Example:
            `deps = registry.factor_dependencies("amplified_conflict_risk")`
        """
        self.ensure_schema()
        sql = "SELECT dependency_name FROM factor_dependencies WHERE factor_name = %s"
        rows = _fetch_all(self.connection, sql, [name])
        return tuple(str(row["dependency_name"]) for row in rows)

    def list_factor_value_artifacts(
        self,
        factor_name: str = "",
        limit: int = 20,
    ) -> tuple[FactorValueArtifact, ...]:
        """List registered Parquet value artifacts.

        Example:
            `artifacts = registry.list_factor_value_artifacts("coverage")`
        """
        self.ensure_schema()
        rows = _fetch_artifact_rows(self.connection, factor_name, limit)
        return tuple(_artifact_from_row(row) for row in rows)

    def latest_factor_value_artifact(
        self,
        factor_name: str,
    ) -> FactorValueArtifact | None:
        """Return the newest registered value artifact for a factor.

        Example:
            `artifact = registry.latest_factor_value_artifact("coverage")`
        """
        artifacts = self.list_factor_value_artifacts(factor_name, limit=1)
        return artifacts[0] if artifacts else None

    def get_factor_value_artifact(
        self,
        artifact_id: int,
        missing_ok: bool = False,
    ) -> FactorValueArtifact | None:
        """Fetch one registered value artifact by id.

        Example:
            `artifact = registry.get_factor_value_artifact(1)`
        """
        self.ensure_schema()
        row = _fetch_one(
            self.connection, "SELECT * FROM factor_values WHERE id = %s", [artifact_id]
        )
        if row is None and missing_ok:
            return None
        if row is None:
            raise KeyError(f"Missing artifact {artifact_id}; expected factor_values id")
        return _artifact_from_row(row)

    def list_factor_evaluations(
        self,
        factor_name: str = "",
        limit: int = 20,
    ) -> tuple[FactorEvaluationRecord, ...]:
        """List recent factor evaluation records.

        Example:
            `records = registry.list_factor_evaluations(limit=10)`
        """
        self.ensure_schema()
        rows = _fetch_evaluation_rows(self.connection, factor_name, limit)
        return tuple(_evaluation_from_row(row) for row in rows)

    def record_factor_values(
        self,
        factor_name: str,
        as_of: object,
        parquet_path: Path,
        row_count: int,
        object_level: str = "",
        time_window_start: object = "",
        time_window_end: object = "",
        content_hash: str = "",
    ) -> None:
        """Record a Parquet value artifact in SQLite.

        Example:
            `registry.record_factor_values("coverage", now, path, 20)`
        """
        self.ensure_schema()
        sql = _insert_values_sql()
        values = [
            factor_name,
            object_level,
            str(time_window_start),
            str(time_window_end),
            str(as_of),
            str(parquet_path),
            row_count,
            content_hash,
        ]
        _execute(self.connection, sql, values)

    def record_factor_evaluation(self, result: FactorScore) -> None:
        """Record one evaluation result.

        Example:
            `registry.record_factor_evaluation(score)`
        """
        self.ensure_schema()
        sql = _insert_evaluation_sql()
        metadata = json.dumps(result.metadata, sort_keys=True)
        values = _evaluation_values(result, metadata)
        _execute(self.connection, sql, values)

    def record_factor_run(self, run: FactorRunRecord) -> None:
        """Record a factor execution run.

        Example:
            `registry.record_factor_run(FactorRunRecord("coverage", "finished"))`
        """
        self.ensure_schema()
        values = _run_values(run)
        _execute(self.connection, _insert_run_sql(), values)

    def list_factor_runs(
        self,
        factor_name: str = "",
        limit: int = 20,
    ) -> tuple[FactorRunRegistryRecord, ...]:
        """List factor execution run rows.

        Example:
            `runs = registry.list_factor_runs("coverage")`
        """
        self.ensure_schema()
        rows = _fetch_run_rows(self.connection, factor_name, limit)
        return tuple(_run_from_row(row) for row in rows)


def ensure_factor_schema(connection: object) -> None:
    """Create factor registry schema with raw SQL.

    Example:
        `ensure_factor_schema(connection)`
    """
    from sourceflow.intelligence.factor_base.migrations_or_init import (
        upgrade_factor_schema,
    )

    upgrade_factor_schema(connection)


def _schema_sql() -> str:
    schema_path = resources.files("sourceflow.intelligence.factor_base").joinpath(
        "schema.sql"
    )
    return schema_path.read_text(encoding="utf-8")


def _schema_statements() -> tuple[str, ...]:
    return tuple(
        statement.strip() for statement in _schema_sql().split(";") if statement.strip()
    )


def _upsert_factor(connection: object, definition: FactorDefinition) -> None:
    payload = json.dumps(expression_to_dict(definition.expression), sort_keys=True)
    values = _factor_values(definition, payload)
    _execute(connection, _upsert_factor_sql(), values)


def _replace_dependencies(connection: object, definition: FactorDefinition) -> None:
    _execute(
        connection,
        "DELETE FROM factor_dependencies WHERE factor_name = %s",
        [definition.name],
    )
    for dependency in factor_dependencies(definition):
        values = [
            dependency.factor_name,
            dependency.dependency_name,
            dependency.dependency_type,
        ]
        _execute(connection, _insert_dependency_sql(), values)


def _definition_from_row(row: dict[str, object]) -> FactorDefinition:
    payload = json.loads(str(row["expression_json"]))
    return FactorDefinition(
        name=str(row["name"]),
        description=str(row["description"]),
        expression=expression_from_dict(payload),
        entity_type=str(row["entity_type"]),
        value_type=str(row["value_type"]),
        status=str(row["status"]),
        slug=str(row.get("slug", "")),
        source=str(row.get("source", "seed")),
        max_depth=int(row.get("max_depth", 0) or 0),
        version=int(row.get("version", 1) or 1),
        notes=str(row.get("notes", "")),
    )


def _artifact_from_row(row: dict[str, object]) -> FactorValueArtifact:
    return FactorValueArtifact(
        id=int(row["id"]),
        factor_name=str(row["factor_name"]),
        as_of=str(row["as_of"]),
        parquet_path=Path(str(row["parquet_path"])),
        row_count=int(row["row_count"]),
        created_at=str(row["created_at"]),
        object_level=str(row.get("object_level", "")),
        time_window_start=str(row.get("time_window_start", "")),
        time_window_end=str(row.get("time_window_end", "")),
        content_hash=str(row.get("content_hash", "")),
    )


def _run_from_row(row: dict[str, object]) -> FactorRunRegistryRecord:
    path = str(row.get("output_parquet_path", ""))
    return FactorRunRegistryRecord(
        id=int(row["id"]),
        factor_name=str(row["factor_name"]),
        run_started_at=str(row["run_started_at"]),
        run_finished_at=str(row["run_finished_at"]),
        status=str(row["status"]),
        row_count=int(row["row_count"]),
        output_parquet_path=Path(path) if path else None,
        error_message=str(row["error_message"]),
    )


def _evaluation_from_row(row: dict[str, object]) -> FactorEvaluationRecord:
    metadata = json.loads(str(row["metadata_json"]))
    return FactorEvaluationRecord(
        id=int(row["id"]),
        factor_name=str(row["factor_name"]),
        objective=str(row["objective"]),
        utility=float(row["utility"]),
        stability=float(row["stability"]),
        novelty=float(row["novelty"]),
        complexity=int(row["complexity"]),
        leakage=float(row["leakage"]),
        score=float(row["score"]),
        metadata=metadata,
        evaluated_at=str(row["evaluated_at"]),
    )


def _factor_values(definition: FactorDefinition, payload: str) -> list[object]:
    text = formula_text(definition.expression)
    return [
        definition.name,
        _factor_slug(definition),
        definition.description,
        payload,
        text,
        text,
        definition.value_type,
        definition.entity_type,
        definition.entity_type,
        definition.value_type,
        definition.status,
        definition.source,
        operator_count(definition.expression),
        definition.max_depth,
        definition.version,
        definition.notes,
    ]


def _evaluation_values(result: FactorScore, metadata: str) -> list[object]:
    return [
        result.factor_name,
        result.objective,
        result.utility,
        result.stability,
        result.novelty,
        result.complexity,
        result.leakage,
        result.score,
        metadata,
    ]


def _run_values(run: FactorRunRecord) -> list[object]:
    return [
        run.factor_name,
        run.run_started_at,
        run.run_finished_at,
        run.status,
        run.row_count,
        str(run.output_parquet_path or ""),
        run.error_message,
    ]


def _upsert_factor_sql() -> str:
    return """
        INSERT INTO factors
        (
            name, slug, description, expression_json, expression_text,
            formula_text, return_type, object_level, entity_type, value_type,
            status, source, complexity, max_depth, version, notes
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT(name) DO UPDATE SET
        slug = excluded.slug,
        description = excluded.description,
        expression_json = excluded.expression_json,
        expression_text = excluded.expression_text,
        formula_text = excluded.formula_text,
        return_type = excluded.return_type,
        object_level = excluded.object_level,
        entity_type = excluded.entity_type,
        value_type = excluded.value_type,
        status = excluded.status,
        source = excluded.source,
        complexity = excluded.complexity,
        max_depth = excluded.max_depth,
        version = excluded.version,
        notes = excluded.notes,
        updated_at = CURRENT_TIMESTAMP
    """


def _insert_dependency_sql() -> str:
    return """
        INSERT OR IGNORE INTO factor_dependencies
        (factor_name, dependency_name, dependency_type)
        VALUES (%s, %s, %s)
    """


def _insert_values_sql() -> str:
    return """
        INSERT INTO factor_values
        (
            factor_name, object_level, time_window_start, time_window_end,
            as_of, parquet_path, row_count, content_hash
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
    """


def _insert_evaluation_sql() -> str:
    return """
        INSERT INTO factor_evaluations
        (
            factor_name, objective, utility, stability, novelty,
            complexity, leakage, score, metadata_json
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
    """


def _insert_run_sql() -> str:
    return """
        INSERT INTO factor_runs
        (
            factor_name, run_started_at, run_finished_at, status,
            row_count, output_parquet_path, error_message
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s)
    """


def _factor_rows_by_status(
    connection: object,
    status: str | None,
    source: str,
) -> list[dict[str, object]]:
    if status is None and not source:
        return _fetch_all(connection, "SELECT * FROM factors ORDER BY name", [])
    if status is None:
        return _fetch_all(
            connection,
            "SELECT * FROM factors WHERE source = %s ORDER BY name",
            [source],
        )
    if source:
        return _fetch_all(
            connection,
            "SELECT * FROM factors WHERE status = %s AND source = %s ORDER BY name",
            [status, source],
        )
    return _fetch_all(
        connection,
        "SELECT * FROM factors WHERE status = %s ORDER BY name",
        [status],
    )


def _fetch_artifact_rows(
    connection: object,
    factor_name: str,
    limit: int,
) -> list[dict[str, object]]:
    if factor_name:
        sql = _artifact_rows_sql("WHERE factor_name = %s")
        return _fetch_all(connection, sql, [factor_name, limit])
    return _fetch_all(connection, _artifact_rows_sql(""), [limit])


def _fetch_evaluation_rows(
    connection: object,
    factor_name: str,
    limit: int,
) -> list[dict[str, object]]:
    if factor_name:
        sql = _evaluation_rows_sql("WHERE factor_name = %s")
        return _fetch_all(connection, sql, [factor_name, limit])
    return _fetch_all(connection, _evaluation_rows_sql(""), [limit])


def _fetch_run_rows(
    connection: object,
    factor_name: str,
    limit: int,
) -> list[dict[str, object]]:
    if factor_name:
        sql = _run_rows_sql("WHERE factor_name = %s")
        return _fetch_all(connection, sql, [factor_name, limit])
    return _fetch_all(connection, _run_rows_sql(""), [limit])


def _artifact_rows_sql(where_clause: str) -> str:
    return f"""
        SELECT * FROM factor_values
        {where_clause}
        ORDER BY id DESC
        LIMIT %s
    """


def _evaluation_rows_sql(where_clause: str) -> str:
    return f"""
        SELECT * FROM factor_evaluations
        {where_clause}
        ORDER BY id DESC
        LIMIT %s
    """


def _run_rows_sql(where_clause: str) -> str:
    return f"""
        SELECT * FROM factor_runs
        {where_clause}
        ORDER BY id DESC
        LIMIT %s
    """


def _table_count(connection: object, table_name: str) -> int:
    if table_name not in _registry_tables():
        raise ValueError(
            f"Invalid table name {table_name}; expected factor registry table"
        )
    row = _fetch_one(connection, f"SELECT COUNT(*) AS count FROM {table_name}", [])
    return int(row["count"] if row else 0)


def _registry_tables() -> tuple[str, ...]:
    return ("factors", "factor_values", "factor_evaluations", "factor_runs")


def _factor_slug(definition: FactorDefinition) -> str:
    if definition.slug:
        return definition.slug
    return definition.name.replace("_", "-")


def _execute(connection: object, sql: str, values: Sequence[object]) -> None:
    with connection.cursor() as cursor:
        cursor.execute(sql, list(values))


def _fetch_one(
    connection: object,
    sql: str,
    values: Sequence[object],
) -> dict[str, object] | None:
    rows = _fetch_all(connection, sql, values)
    return rows[0] if rows else None


def _fetch_all(
    connection: object,
    sql: str,
    values: Sequence[object],
) -> list[dict[str, object]]:
    with connection.cursor() as cursor:
        cursor.execute(sql, list(values))
        columns = [column[0] for column in cursor.description or ()]
        return [dict(zip(columns, row, strict=True)) for row in cursor.fetchall()]
