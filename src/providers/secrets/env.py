"""Environment-backed secret provider."""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass

from src.providers.base import ProviderError


@dataclass(frozen=True, slots=True)
class EnvSecretProvider:
    """Read secrets from an injected mapping or process environment.

    Example:
        `EnvSecretProvider({"TOKEN": "x"}).require("TOKEN")`
    """

    env: Mapping[str, str] | None = None

    def get(self, name: str, default: str | None = None) -> str | None:
        """Return an environment secret or default."""
        source = os.environ if self.env is None else self.env
        return source.get(name, default)

    def require(self, name: str) -> str:
        """Return a required environment secret."""
        value = self.get(name)
        if value:
            return value
        raise ProviderError(f"Invalid secret {name!r}; expected configured value")
