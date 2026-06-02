"""Hugging Face model registry boundary stub."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from src.providers.base import MissingProviderDependencyError


@dataclass(frozen=True, slots=True)
class HuggingFaceModelRegistryStub:
    """Explicit optional boundary for future Hugging Face model artifacts.

    Example:
        `HuggingFaceModelRegistryStub().list_models()`
    """

    def save_model(
        self,
        name: str,
        version: str,
        local_path: Path,
        metadata: Mapping[str, object],
    ) -> dict[str, object]:
        """Fail clearly until the optional Hub adapter is implemented."""
        raise _missing_huggingface_adapter()

    def load_model(self, name: str, version: str | None = None) -> dict[str, object]:
        """Fail clearly until the optional Hub adapter is implemented."""
        raise _missing_huggingface_adapter()

    def list_models(self, name: str | None = None) -> list[dict[str, object]]:
        """Fail clearly until the optional Hub adapter is implemented."""
        raise _missing_huggingface_adapter()

    def resolve_artifact_uri(self, name: str, version: str | None = None) -> str:
        """Fail clearly until the optional Hub adapter is implemented."""
        raise _missing_huggingface_adapter()


def _missing_huggingface_adapter() -> MissingProviderDependencyError:
    return MissingProviderDependencyError(
        "huggingface_hub is required by Hugging Face model registry; "
        "expected installed module"
    )
