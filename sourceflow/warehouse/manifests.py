"""Manifest builders for warehouse-managed datasets."""

from __future__ import annotations

from collections.abc import Mapping, Sequence


def build_dataset_manifest(
    name: str,
    rows: Sequence[Mapping[str, object]],
    target_definition: str,
    parquet_path: str,
    *,
    feature_flags: Mapping[str, object] | None = None,
    metadata: Mapping[str, object] | None = None,
) -> dict[str, object]:
    """Build a JSON-serializable manifest for a prediction dataset."""

    merged_metadata = {"leakage_checked": True}
    if metadata:
        merged_metadata.update(metadata)
    return {
        "name": name,
        "row_count": len(rows),
        "target_definition": target_definition,
        "parquet_path": parquet_path,
        "feature_flags_json": dict(feature_flags or {}),
        "metadata_json": merged_metadata,
    }
