"""Parquet feature matrix storage for Quant4 multifractal features."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class FeatureMatrixWriteResult:
    """Feature matrix storage result.

    Example:
        `result = write_feature_matrix(rows, Path("features"), "mf", {})`
    """

    artifact_path: str
    row_count: int
    config_hash: str


def write_feature_matrix(
    rows: Sequence[Mapping[str, object]],
    root_path: Path,
    feature_set_name: str,
    config: Mapping[str, object],
) -> FeatureMatrixWriteResult:
    """Write a feature matrix to Parquet and register `FeatureArtifact`.

    Example:
        `result = write_feature_matrix(rows, Path("data/features"), "mf_core", {})`
    """
    validated = _validate_rows(rows)
    root_path.mkdir(parents=True, exist_ok=True)
    artifact_path = root_path / "feature-matrix.parquet"
    _write_rows([_arrow_row(row) for row in validated], artifact_path)
    digest = _config_hash(config)
    _register_feature_artifact(feature_set_name, str(artifact_path), config, digest)
    return FeatureMatrixWriteResult(str(artifact_path), len(validated), digest)


def read_feature_matrix_parquet(artifact_path: str) -> list[dict[str, object]]:
    """Read a stored Parquet feature matrix.

    Example:
        `rows = read_feature_matrix_parquet("data/features/feature-matrix.parquet")`
    """
    _pyarrow, parquet = _arrow_modules()
    return list(parquet.ParquetFile(artifact_path).read().to_pylist())


def _register_feature_artifact(
    feature_set_name: str,
    artifact_path: str,
    config: Mapping[str, object],
    digest: str,
) -> None:
    from quant4.models import FeatureArtifact

    FeatureArtifact.objects.update_or_create(
        feature_set_name=feature_set_name,
        artifact_uri=artifact_path,
        defaults={
            "config_json": dict(config),
            "config_hash": digest,
            "random_seed": int(config.get("random_seed", 0)),
            "feature_schema_json": {"columns": list(config.get("columns", []))},
            "provenance_json": {"engine": "quant4_multifractal_features"},
        },
    )


def _validate_rows(rows: Sequence[Mapping[str, object]]) -> list[Mapping[str, object]]:
    if rows:
        return list(rows)
    raise ValueError(f"Invalid feature rows {rows!r}; expected at least one row")


def _write_rows(rows: list[dict[str, object]], output_path: Path) -> None:
    pyarrow, parquet = _arrow_modules()
    parquet.write_table(pyarrow.Table.from_pylist(rows), output_path)


def _arrow_row(row: Mapping[str, object]) -> dict[str, object]:
    return {key: _arrow_value(value) for key, value in row.items()}


def _arrow_value(value: object) -> object:
    if isinstance(value, dict | list | tuple):
        return json.dumps(value, sort_keys=True, default=str)
    return value


def _config_hash(config: Mapping[str, object]) -> str:
    raw = json.dumps(dict(config), sort_keys=True, default=str)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:24]


def _arrow_modules() -> tuple[object, object]:
    try:
        import pyarrow
        import pyarrow.parquet
    except ImportError as exc:
        raise RuntimeError(
            "Feature store failed; expected pyarrow installed for Parquet output"
        ) from exc
    return pyarrow, pyarrow.parquet
