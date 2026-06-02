"""Object-storage-backed model registry."""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from src.providers.model_registry.local import _safe_token
from src.providers.storage.base import StorageProvider


@dataclass(frozen=True, slots=True)
class ObjectStoreModelRegistryProvider:
    """Store model artifacts through the configured object storage provider.

    Example:
        `ObjectStoreModelRegistryProvider(storage).list_models()`
    """

    storage: StorageProvider
    prefix: str = "models"

    def save_model(
        self,
        name: str,
        version: str,
        local_path: Path,
        metadata: Mapping[str, object],
    ) -> dict[str, object]:
        """Upload model bytes and metadata to object storage."""
        artifact_key = self._artifact_key(name, version, local_path.name)
        artifact_uri = self.storage.put_bytes(artifact_key, local_path.read_bytes())
        record = _record(name, version, artifact_uri, metadata)
        self.storage.put_bytes(self._manifest_key(name, version), _json_bytes(record))
        return record

    def load_model(self, name: str, version: str | None = None) -> dict[str, object]:
        """Load object-store model metadata."""
        resolved_version = version or self._latest_version(name)
        manifest_key = self._manifest_key(name, resolved_version)
        return json.loads(self.storage.get_bytes(manifest_key))

    def list_models(self, name: str | None = None) -> list[dict[str, object]]:
        """List object-store model metadata."""
        prefix = self._name_prefix(name) if name else self.prefix
        manifests = [
            path for path in self.storage.list(prefix) if path.endswith("manifest.json")
        ]
        return [json.loads(self.storage.get_bytes(path)) for path in sorted(manifests)]

    def resolve_artifact_uri(self, name: str, version: str | None = None) -> str:
        """Return a model artifact URI."""
        return str(self.load_model(name, version)["artifact_uri"])

    def _artifact_key(self, name: str, version: str, filename: str) -> str:
        return f"{self._version_prefix(name, version)}/{_safe_token(filename)}"

    def _manifest_key(self, name: str, version: str) -> str:
        return f"{self._version_prefix(name, version)}/manifest.json"

    def _name_prefix(self, name: str) -> str:
        return f"{self.prefix}/{_safe_token(name)}"

    def _version_prefix(self, name: str, version: str) -> str:
        return f"{self._name_prefix(name)}/{_safe_token(version)}"

    def _latest_version(self, name: str) -> str:
        manifests = self.storage.list(self._name_prefix(name))
        versions = sorted(
            path.split("/")[-2]
            for path in manifests
            if path.endswith("manifest.json")
        )
        if versions:
            return versions[-1]
        raise ValueError(f"Invalid model name {name!r}; expected registered model")


def _record(
    name: str,
    version: str,
    artifact_uri: str,
    metadata: Mapping[str, object],
) -> dict[str, object]:
    return {
        "name": name,
        "version": version,
        "artifact_uri": artifact_uri,
        "metadata": dict(metadata),
        "provider": "object_store",
    }


def _json_bytes(record: Mapping[str, object]) -> bytes:
    return json.dumps(record, sort_keys=True).encode("utf-8")
