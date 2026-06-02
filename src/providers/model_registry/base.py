"""Model registry provider interface."""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Protocol


class ModelRegistryProvider(Protocol):
    """Pre-trained model artifact registry boundary.

    Example:
        `registry.save_model("mamba", "v1", Path("model.bin"), {})`
    """

    def save_model(
        self,
        name: str,
        version: str,
        local_path: Path,
        metadata: Mapping[str, object],
    ) -> dict[str, object]:
        """Save a model artifact and return registry metadata."""

    def load_model(self, name: str, version: str | None = None) -> dict[str, object]:
        """Load metadata for a model artifact."""

    def list_models(self, name: str | None = None) -> list[dict[str, object]]:
        """List registered models."""

    def resolve_artifact_uri(self, name: str, version: str | None = None) -> str:
        """Return the artifact URI for a model version."""
