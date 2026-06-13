"""DuckDB context for partitioned Parquet analytics."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from glob import glob
from pathlib import Path

from src.providers.base import MissingProviderDependencyError, ProviderError


@dataclass(frozen=True, slots=True)
class ColumnSpec:
    """Canonical view column mapping for heterogeneous Parquet files.

    Example:
        `ColumnSpec("ts", "TIMESTAMP", ("ts", "timestamp"), "NULL")`
    """

    name: str
    type_sql: str
    aliases: tuple[str, ...]
    default_sql: str = "NULL"


@dataclass(frozen=True, slots=True)
class MirrorResult:
    """Object-store mirror result for DuckDB local scans.

    Example:
        `result.local_root`
    """

    local_root: Path
    object_count: int
    byte_count: int


@dataclass(slots=True)
class DuckDBWarehouseContext:
    """Manage DuckDB connections, views, and local Parquet scan roots.

    Example:
        `DuckDBWarehouseContext(Path("data/lake/analytics.duckdb"), Path("data/lake"))`
    """

    database_path: Path
    lake_root: Path
    cache_root: Path | None = None
    _connection: object | None = field(default=None, init=False, repr=False)

    def connect(self) -> object:
        """Return a reusable DuckDB connection."""
        if self._connection is None:
            duckdb = _duckdb_module()
            if str(self.database_path) != ":memory:":
                self.database_path.parent.mkdir(parents=True, exist_ok=True)
            self._connection = duckdb.connect(str(self.database_path))
            self.execute("set timezone='UTC'")
        return self._connection

    def close(self) -> None:
        """Close the DuckDB connection if it was opened."""
        if self._connection is not None:
            self._connection.close()
            self._connection = None

    def __enter__(self) -> DuckDBWarehouseContext:
        """Open a context-managed warehouse connection."""
        self.connect()
        return self

    def __exit__(self, *args: object) -> None:
        """Close a context-managed warehouse connection."""
        self.close()

    def execute(
        self,
        sql: str,
        params: Sequence[object] | None = None,
    ) -> object:
        """Execute SQL without loading result sets into pandas."""
        return self.connect().execute(sql, list(params or []))

    def query(
        self,
        sql: str,
        params: Sequence[object] | None = None,
    ) -> list[dict[str, object]]:
        """Run SQL and return row dictionaries for small control-plane results."""
        result = self.execute(sql, params)
        columns = [column[0] for column in result.description or []]
        return [dict(zip(columns, row, strict=False)) for row in result.fetchall()]

    def scalar(self, sql: str, params: Sequence[object] | None = None) -> object:
        """Return the first value from a SQL query."""
        return self.execute(sql, params).fetchone()[0]

    def materialize(self, sql: str, output_path: str | Path) -> Path:
        """Write a DuckDB query result directly to Parquet."""
        path = Path(output_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        copy_sql = f"copy ({sql}) to {sql_literal(path)} (format parquet)"
        self.execute(copy_sql)
        return path

    def create_parquet_view(
        self,
        view_name: str,
        globs: Sequence[str | Path],
        columns: Sequence[ColumnSpec],
    ) -> None:
        """Create a canonical view over existing Parquet files or an empty schema."""
        _validate_identifier(view_name)
        paths = _existing_parquet_paths(globs)
        if not paths:
            self.execute(_empty_view_sql(view_name, columns))
            return
        available_columns = _describe_parquet_columns(self, paths)
        select_list = [
            _column_select_expression(spec, available_columns) for spec in columns
        ]
        relation = _read_parquet_relation(paths)
        self.execute(
            "create or replace view "
            f"{quote_identifier(view_name)} as select {', '.join(select_list)} "
            f"from {relation}"
        )

    def mirror_storage_prefixes(
        self,
        storage_provider: object,
        prefixes: Sequence[str],
    ) -> MirrorResult:
        """Mirror object-store Parquet partitions to local cache for DuckDB scans."""
        cache_root = self.cache_root or self.lake_root / "_cache" / "object_store"
        object_count = 0
        byte_count = 0
        for prefix in prefixes:
            for key in _parquet_keys(storage_provider.list(prefix)):
                data = storage_provider.get_bytes(key)
                target = _safe_cache_path(cache_root, key)
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(data)
                object_count += 1
                byte_count += len(data)
        return MirrorResult(cache_root, object_count, byte_count)


def default_dataset_globs(lake_root: str | Path) -> dict[str, list[str]]:
    """Return Parquet globs for the canonical data lake layout."""
    root = Path(lake_root)
    return {
        "market_bars": [
            str(root / "raw" / "**" / "*.parquet"),
            str(root / "bronze" / "market_bars" / "**" / "*.parquet"),
            str(root / "silver" / "market_bars" / "**" / "*.parquet"),
        ],
        "features": [
            str(root / "features" / "**" / "*.parquet"),
            str(root / "silver" / "features" / "**" / "*.parquet"),
        ],
        "lob_features": [
            str(root / "features" / "lob" / "**" / "*.parquet"),
            str(root / "bronze" / "lob" / "**" / "*.parquet"),
            str(root / "silver" / "lob" / "**" / "*.parquet"),
        ],
        "predictions": [
            str(root / "predictions" / "**" / "*.parquet"),
            str(root / "gold" / "predictions" / "**" / "*.parquet"),
        ],
        "portfolio_weights": [
            str(root / "backtests" / "portfolio_weights" / "**" / "*.parquet"),
            str(root / "gold" / "portfolio_weights" / "**" / "*.parquet"),
        ],
        "backtests": [
            str(root / "backtests" / "**" / "*.parquet"),
            str(root / "gold" / "backtests" / "**" / "*.parquet"),
        ],
        "risk": [
            str(root / "risk" / "**" / "*.parquet"),
            str(root / "gold" / "risk" / "**" / "*.parquet"),
        ],
    }


def sql_literal(value: object) -> str:
    """Return a single-quoted SQL literal for DuckDB control SQL."""
    if value is None:
        return "NULL"
    return "'" + str(value).replace("'", "''") + "'"


def quote_identifier(value: str) -> str:
    """Return a double-quoted SQL identifier."""
    return '"' + value.replace('"', '""') + '"'


def _duckdb_module() -> object:
    try:
        import duckdb
    except ImportError as exc:
        raise MissingProviderDependencyError(
            "duckdb is required by the warehouse analytical layer; "
            "expected installed module"
        ) from exc
    return duckdb


def _existing_parquet_paths(globs: Sequence[str | Path]) -> list[Path]:
    paths: list[Path] = []
    for pattern in globs:
        value = str(pattern)
        path = Path(value)
        if path.is_file() and path.suffix == ".parquet":
            paths.append(path)
            continue
        paths.extend(Path(match) for match in glob(value, recursive=True))
    return sorted({path.resolve() for path in paths if path.is_file()})


def _describe_parquet_columns(
    context: DuckDBWarehouseContext,
    paths: Sequence[Path],
) -> set[str]:
    sql = f"describe select * from {_read_parquet_relation(paths)}"
    rows = context.execute(sql).fetchall()
    return {str(row[0]) for row in rows}


def _read_parquet_relation(paths: Sequence[Path]) -> str:
    values = ", ".join(sql_literal(path.as_posix()) for path in paths)
    return f"read_parquet([{values}], hive_partitioning=true, union_by_name=true)"


def _empty_view_sql(view_name: str, columns: Sequence[ColumnSpec]) -> str:
    select_list = [
        f"cast({spec.default_sql} as {spec.type_sql}) as {quote_identifier(spec.name)}"
        for spec in columns
    ]
    return (
        f"create or replace view {quote_identifier(view_name)} as "
        f"select {', '.join(select_list)} where false"
    )


def _column_select_expression(spec: ColumnSpec, available_columns: set[str]) -> str:
    terms = [
        _cast_column(candidate, spec.type_sql)
        for candidate in spec.aliases
        if candidate in available_columns
    ]
    terms.append(f"cast({spec.default_sql} as {spec.type_sql})")
    return f"coalesce({', '.join(terms)}) as {quote_identifier(spec.name)}"


def _cast_column(column_name: str, type_sql: str) -> str:
    identifier = quote_identifier(column_name)
    if type_sql.upper() == "VARCHAR":
        return f"cast({identifier} as VARCHAR)"
    return f"try_cast({identifier} as {type_sql})"


def _validate_identifier(value: str) -> None:
    valid_body = value.replace("_", "").isalnum()
    valid_start = bool(value) and (value[0].isalpha() or value[0] == "_")
    if valid_body and valid_start:
        return
    raise ProviderError(f"Invalid DuckDB identifier {value!r}")


def _parquet_keys(keys: Sequence[str]) -> list[str]:
    return sorted(key for key in keys if key.endswith(".parquet"))


def _safe_cache_path(cache_root: Path, key: str) -> Path:
    normalized = key.strip().replace("\\", "/").strip("/")
    target = (cache_root / normalized).resolve()
    root = cache_root.resolve()
    if target == root or root in target.parents:
        return target
    raise ProviderError(f"Invalid object-store key {key!r}; expected relative path")
