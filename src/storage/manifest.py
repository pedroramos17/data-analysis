"""Manifest helpers for data lake and model artifact objects."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any


@dataclass(frozen=True, slots=True)
class DatasetManifest:
    """Manifest written next to a stored dataset partition or artifact version.

    Example:
        `manifest = build_manifest(b"abc", [], 1, "unit-test")`
    """

    schema: Sequence[Mapping[str, object]]
    row_count: int
    source: str
    created_at: str
    content_hash: str
    dataset: str = ""
    version: str = ""
    partition: Mapping[str, str] = field(default_factory=dict)
    object_path: str = ""
    object_uri: str = ""
    metadata: Mapping[str, object] = field(default_factory=dict)

    def to_dict(self) -> dict[str, object]:
        """Return a JSON-serializable manifest dictionary."""
        return {
            "schema": [dict(item) for item in self.schema],
            "row_count": self.row_count,
            "source": self.source,
            "created_at": self.created_at,
            "content_hash": self.content_hash,
            "dataset": self.dataset,
            "version": self.version,
            "partition": dict(self.partition),
            "object_path": self.object_path,
            "object_uri": self.object_uri,
            "metadata": dict(self.metadata),
        }

    def to_json_bytes(self) -> bytes:
        """Return deterministic manifest JSON bytes."""
        payload = json.dumps(self.to_dict(), sort_keys=True, indent=2, default=str)
        return payload.encode("utf-8")


def build_manifest(
    data: bytes,
    schema: Sequence[Mapping[str, object]],
    row_count: int,
    source: str,
    *,
    dataset: str = "",
    version: str = "",
    partition: Mapping[str, str] | None = None,
    object_path: str = "",
    object_uri: str = "",
    metadata: Mapping[str, object] | None = None,
) -> DatasetManifest:
    """Build a manifest for bytes written through a storage provider."""
    if row_count < 0:
        raise ValueError(f"Invalid row_count {row_count!r}; expected non-negative")
    return DatasetManifest(
        schema=schema,
        row_count=row_count,
        source=source,
        created_at=datetime.now(UTC).isoformat(),
        content_hash=content_hash(data),
        dataset=dataset,
        version=version,
        partition=dict(partition or {}),
        object_path=object_path,
        object_uri=object_uri,
        metadata=dict(metadata or {}),
    )


def content_hash(data: bytes) -> str:
    """Return a stable SHA-256 hash label for stored content."""
    return "sha256:" + hashlib.sha256(data).hexdigest()


def manifest_from_json(data: bytes) -> dict[str, Any]:
    """Decode a stored manifest JSON payload."""
    loaded = json.loads(data.decode("utf-8"))
    if isinstance(loaded, dict):
        return loaded
    raise ValueError("Invalid manifest payload; expected JSON object")
