"""Local filesystem model registry."""

from __future__ import annotations

import json
import shutil
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from src.providers.base import ProviderError


@dataclass(frozen=True, slots=True)
class LocalModelRegistryProvider:
    """Store model artifacts and metadata under a local cache root.

    Example:
        `LocalModelRegistryProvider(Path("models")).list_models()`
    """

    root: Path

    def save_model(
        self,
        name: str,
        version: str,
        local_path: Path,
        metadata: Mapping[str, object],
    ) -> dict[str, object]:
        """Copy a local model artifact into the registry."""
        target = self._version_dir(name, version) / local_path.name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(local_path, target)
        record = _model_record(name, version, target, metadata)
        _write_json(self._manifest_path(name, version), record)
        return record

    def load_model(self, name: str, version: str | None = None) -> dict[str, object]:
        """Load local registry metadata."""
        resolved_version = version or self._latest_version(name)
        return _read_json(self._manifest_path(name, resolved_version))

    def list_models(self, name: str | None = None) -> list[dict[str, object]]:
        """List local model registry metadata."""
        roots = [self.root / name] if name else sorted(self.root.glob("*"))
        manifests = [path for root in roots for path in root.glob("*/manifest.json")]
        return [_read_json(path) for path in sorted(manifests)]

    def resolve_artifact_uri(self, name: str, version: str | None = None) -> str:
        """Return the local artifact URI for a model version."""
        record = self.load_model(name, version)
        return str(record["artifact_uri"])

    def _version_dir(self, name: str, version: str) -> Path:
        return self.root / _safe_token(name) / _safe_token(version)

    def _manifest_path(self, name: str, version: str) -> Path:
        return self._version_dir(name, version) / "manifest.json"

    def _latest_version(self, name: str) -> str:
        model_root = self.root / _safe_token(name)
        versions = sorted(path.name for path in model_root.glob("*"))
        if versions:
            return versions[-1]
        raise ProviderError(f"Invalid model name {name!r}; expected registered model")


def _model_record(
    name: str,
    version: str,
    artifact_path: Path,
    metadata: Mapping[str, object],
) -> dict[str, object]:
    return {
        "name": name,
        "version": version,
        "artifact_uri": artifact_path.resolve().as_uri(),
        "metadata": dict(metadata),
        "provider": "local",
    }


def _write_json(path: Path, record: Mapping[str, object]) -> None:
    path.write_text(json.dumps(record, sort_keys=True, indent=2), encoding="utf-8")


def _read_json(path: Path) -> dict[str, object]:
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    raise ProviderError(f"Invalid model manifest {path!s}; expected existing file")


def _safe_token(value: str) -> str:
    token = "".join(char if char.isalnum() or char in "-_" else "_" for char in value)
    return token.strip("_") or "unnamed"
