"""Training manifest helpers for finance models."""

from __future__ import annotations


def training_manifest(
    dataset_path: str,
    model_type: str,
    metrics: dict[str, float] | None = None,
) -> dict[str, object]:
    """Build a JSON-serializable training manifest.

    Example:
        `manifest = training_manifest("x.parquet", "ridge")`
    """
    return {
        "dataset_path": dataset_path,
        "model_type": model_type,
        "metrics": metrics or {},
        "validation": "walk_forward_purged_embargoed",
    }
