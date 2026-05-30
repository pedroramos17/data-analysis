"""Prediction dataset manifest helpers."""

from __future__ import annotations

from collections.abc import Mapping, Sequence


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
    return {
        "name": name,
        "row_count": len(rows),
        "target_definition": target_definition,
        "parquet_path": parquet_path,
        "feature_flags_json": {},
        "metadata_json": {"leakage_checked": True},
    }
