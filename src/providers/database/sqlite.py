"""SQLite database provider."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass

from src.config.settings import DatabaseSettings


@dataclass(frozen=True, slots=True)
class SqliteDatabaseProvider:
    """SQLite metadata provider for local/offline mode.

    Example:
        `SqliteDatabaseProvider(settings).healthcheck()`
    """

    settings: DatabaseSettings

    def get_engine(self) -> sqlite3.Connection:
        """Return a SQLite connection."""
        return sqlite3.connect(
            self.settings.sqlite_path,
            timeout=self.settings.sqlite_timeout_seconds,
        )

    def run_migrations(self) -> dict[str, object]:
        """Describe migration ownership for Django-managed SQLite."""
        return {"status": "managed_by_django", "provider": "sqlite"}

    def healthcheck(self) -> bool:
        """Return whether SQLite can answer a trivial query."""
        connection = self.get_engine()
        try:
            return connection.execute("select 1").fetchone() == (1,)
        finally:
            connection.close()
