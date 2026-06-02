"""Database provider interface."""

from __future__ import annotations

from typing import Protocol


class DatabaseProvider(Protocol):
    """Transactional metadata database boundary.

    Example:
        `provider.healthcheck()`
    """

    def get_engine(self) -> object:
        """Return the provider-specific connection or engine."""

    def run_migrations(self) -> dict[str, object]:
        """Run or describe migrations for this database provider."""

    def healthcheck(self) -> bool:
        """Return whether the database is reachable."""
