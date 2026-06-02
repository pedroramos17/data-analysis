"""Postgres database provider."""

from __future__ import annotations

from dataclasses import dataclass

from src.config.settings import DatabaseSettings
from src.providers.base import MissingProviderDependencyError


@dataclass(frozen=True, slots=True)
class PostgresDatabaseProvider:
    """Postgres provider for cloud transactional metadata.

    Example:
        `PostgresDatabaseProvider(settings).healthcheck()`
    """

    settings: DatabaseSettings

    def get_engine(self) -> object:
        """Return a psycopg connection when the optional driver is installed."""
        psycopg = _psycopg_module()
        return psycopg.connect(self.settings.postgres_url)

    def run_migrations(self) -> dict[str, object]:
        """Describe migration ownership for Django-managed Postgres."""
        return {"status": "managed_by_django", "provider": "postgres"}

    def healthcheck(self) -> bool:
        """Return whether Postgres can answer a trivial query."""
        connection = self.get_engine()
        try:
            with connection.cursor() as cursor:
                cursor.execute("select 1")
                return cursor.fetchone() == (1,)
        finally:
            connection.close()


def _psycopg_module() -> object:
    try:
        import psycopg
    except ImportError as exc:
        raise MissingProviderDependencyError(
            "psycopg is required by Postgres provider; expected installed module"
        ) from exc
    return psycopg
