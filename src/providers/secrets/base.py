"""Secret provider interface."""

from __future__ import annotations

from typing import Protocol


class SecretProvider(Protocol):
    """Runtime secret lookup boundary.

    Example:
        `secrets.require("DATABASE_URL")`
    """

    def get(self, name: str, default: str | None = None) -> str | None:
        """Return a secret value or default."""

    def require(self, name: str) -> str:
        """Return a required secret or raise a clear error."""
