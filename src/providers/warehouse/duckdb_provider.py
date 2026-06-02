"""DuckDB warehouse provider over Parquet artifacts."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from src.config.settings import DuckDBSettings
from src.providers.base import MissingProviderDependencyError, ProviderError


@dataclass(frozen=True, slots=True)
class DuckDBWarehouseProvider:
    """DuckDB OLAP provider for local Parquet analytics.

    Example:
        `DuckDBWarehouseProvider(settings).query("select 1")`
    """

    settings: DuckDBSettings

    def connect(self) -> object:
        """Return a DuckDB connection when the optional module is installed."""
        duckdb = _duckdb_module()
        self.settings.database_path.parent.mkdir(parents=True, exist_ok=True)
        return duckdb.connect(str(self.settings.database_path))

    def register_parquet_table(self, name: str, path_or_glob: str) -> None:
        """Register a Parquet path or glob as a DuckDB view."""
        _validate_table_name(name)
        connection = self.connect()
        try:
            connection.execute(_create_parquet_view_sql(name), [path_or_glob])
        finally:
            connection.close()

    def query(
        self,
        sql: str,
        params: Sequence[object] | None = None,
    ) -> list[dict[str, object]]:
        """Run SQL and return row dictionaries."""
        connection = self.connect()
        try:
            result = connection.execute(sql, list(params or []))
            columns = [column[0] for column in result.description or []]
            return [_row_dict(columns, row) for row in result.fetchall()]
        finally:
            connection.close()

    def materialize(self, sql: str, output_path: str) -> str:
        """Write query results to a Parquet file."""
        connection = self.connect()
        try:
            copy_sql = "copy (" + sql + ") to ? (format parquet)"
            connection.execute(copy_sql, [output_path])
        finally:
            connection.close()
        return output_path


def _duckdb_module() -> object:
    try:
        import duckdb
    except ImportError as exc:
        raise MissingProviderDependencyError(
            "duckdb is required by DuckDB warehouse; expected installed module"
        ) from exc
    return duckdb


def _validate_table_name(name: str) -> None:
    if name.replace("_", "").isalnum() and name[0].isalpha():
        return
    raise ProviderError(f"Invalid table name {name!r}; expected SQL identifier")


def _create_parquet_view_sql(name: str) -> str:
    return f"create or replace view {name} as select * from read_parquet(?)"


def _row_dict(columns: Sequence[str], row: Sequence[object]) -> dict[str, object]:
    return dict(zip(columns, row, strict=False))
