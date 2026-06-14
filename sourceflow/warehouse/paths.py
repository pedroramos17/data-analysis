"""Path helpers for partitioned warehouse artifacts."""

from __future__ import annotations

from pathlib import Path


def partition_path(root: str | Path, **parts: object) -> Path:
    """Build a deterministic partition path from key-value parts."""

    path = Path(root)
    for key, value in parts.items():
        path = path / f"{key}={_safe_part(value)}"
    return path


def _safe_part(value: object) -> str:
    return str(value).strip().replace("/", "_").replace(" ", "_")
