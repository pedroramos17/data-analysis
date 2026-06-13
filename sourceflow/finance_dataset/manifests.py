"""Prediction dataset manifest helpers."""

from __future__ import annotations

from collections.abc import Mapping, Sequence

from sourceflow.warehouse.manifests import build_dataset_manifest


def build_manifest(
    name: str,
    rows: Sequence[Mapping[str, object]],
    target_definition: str,
    parquet_path: str,
) -> dict[str, object]:
    """Build a JSON-serializable prediction dataset manifest.

    Example:
        `manifest = build_manifest("demo", rows, "forward_return", "x.parquet")`
    """
    return build_dataset_manifest(name, rows, target_definition, parquet_path)
