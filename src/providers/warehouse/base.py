"""Analytical warehouse provider interface."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol


class WarehouseProvider(Protocol):
    """OLAP query boundary over Parquet artifacts.

    Example:
        `warehouse.query("select 1")`
    """

    def connect(self) -> object:
        """Return the provider-specific warehouse connection."""

    def register_parquet_table(self, name: str, path_or_glob: str) -> None:
        """Register a Parquet path or glob as a table."""

    def query(
        self,
        sql: str,
        params: Sequence[object] | None = None,
    ) -> list[dict[str, object]]:
        """Run SQL and return row dictionaries."""

    def materialize(self, sql: str, output_path: str) -> str:
        """Write a query result to an output artifact."""
