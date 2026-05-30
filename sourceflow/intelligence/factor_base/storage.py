"""Parquet storage for factor values."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path


class FactorValueStorage:
    """Write and read factor value rows from Parquet files.

    Example:
        `storage = FactorValueStorage(Path("exports/factors"))`
    """

    def __init__(self, output_dir: Path) -> None:
        """Create a storage boundary rooted at one directory.

        Example:
            `FactorValueStorage(Path("exports/factors"))`
        """
        self.output_dir = output_dir

    def write_values(
        self,
        factor_name: str,
        rows: list[dict[str, object]],
    ) -> Path:
        """Write factor values and return the Parquet path.

        Example:
            `path = storage.write_values("coverage", rows)`
        """
        pyarrow, parquet = _arrow_modules()
        path = self._factor_path(factor_name)
        path.parent.mkdir(parents=True, exist_ok=True)
        table = pyarrow.Table.from_pylist(rows)
        parquet.write_table(table, path)
        return path

    def read_values(self, path: Path) -> list[dict[str, object]]:
        """Read factor values from a Parquet path.

        Example:
            `rows = storage.read_values(path)`
        """
        if not path.exists():
            raise RuntimeError(f"Missing factor parquet {path}; expected existing file")
        _pyarrow, parquet = _arrow_modules()
        table = parquet.read_table(path)
        return list(table.to_pylist())

    def latest_path(self, factor_name: str) -> Path | None:
        """Return the newest local Parquet file for a factor.

        Example:
            `path = storage.latest_path("coverage_intensity")`
        """
        directory = self.output_dir / factor_name
        paths = sorted(directory.glob("*.parquet"))
        return paths[-1] if paths else None

    def _factor_path(self, factor_name: str) -> Path:
        stamp = datetime.utcnow().strftime("%Y%m%d%H%M%S%f")
        return self.output_dir / factor_name / f"{stamp}.parquet"


def _arrow_modules() -> tuple[object, object]:
    try:
        import pyarrow
        import pyarrow.parquet
    except ImportError as error:
        raise RuntimeError(
            "Factor storage failed; expected pyarrow installed"
        ) from error
    return pyarrow, pyarrow.parquet
