"""Alembic environment for the Quant MVP compatibility schema."""

from __future__ import annotations

import os
from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

from src.config.settings import load_runtime_settings
from src.database.core_schema import metadata, sqlalchemy_url_from_database_settings

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = metadata


def _migration_database_url() -> str:
    env_url = os.environ.get("DATABASE_URL", "").strip()
    if env_url:
        return _postgres_sqlalchemy_url(env_url)
    settings = load_runtime_settings()
    return sqlalchemy_url_from_database_settings(settings.database)


def _postgres_sqlalchemy_url(database_url: str) -> str:
    if database_url.startswith("postgresql://"):
        return "postgresql+psycopg://" + database_url.removeprefix("postgresql://")
    if database_url.startswith("postgres://"):
        return "postgresql+psycopg://" + database_url.removeprefix("postgres://")
    return database_url


def run_migrations_offline() -> None:
    """Run migrations in offline SQL-emission mode."""
    context.configure(
        url=_migration_database_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations against a live SQLite or Postgres database."""
    config.set_main_option("sqlalchemy.url", _migration_database_url())
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
