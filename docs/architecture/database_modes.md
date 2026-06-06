# Database Modes

The project supports two transactional metadata modes while preserving SQLite as
the local default.

## SQLite Mode

SQLite is selected by default with:

```text
APP_ENV=local
DEPLOYMENT_MODE=onprem
DB_MODE=sqlite
SQLITE_PATH=./db.sqlite3
```

SQLite backs local Django metadata and the SQLAlchemy compatibility schema. The
SQLite provider is dependency-free and returns `managed_by_django` for provider
migration ownership.

## Postgres Mode

Postgres is selected with:

```text
APP_ENV=cloud
DEPLOYMENT_MODE=cloud_mvp
DB_MODE=postgres
DATABASE_URL=postgresql://user:password@host:5432/database
```

Alternatively, set `POSTGRES_DB`, `POSTGRES_USER`, `POSTGRES_PASSWORD`,
`POSTGRES_HOST`, optional `POSTGRES_PORT`, and optional `POSTGRES_SSLMODE`.

Postgres provider health checks require optional `psycopg`. SQLAlchemy uses the
compatibility URL helper to convert `postgresql://` to `postgresql+psycopg://`
for SQLAlchemy engines.

## Compatibility Schema

The additive SQLAlchemy/Alembic compatibility schema contains MVP tables for
assets, ingestion runs, bars, features, signals, model artifacts, backtests, and
risk runs. Django migrations remain authoritative for the web app.

Run locally:

```bash
python -m src.cli db migrate
```

or directly:

```bash
alembic -c alembic.ini upgrade head
```

## Testing

SQLite tests run by default. Postgres connectivity tests must be explicitly
enabled with `ENABLE_CLOUD_TESTS=true` and a `POSTGRES_TEST_DATABASE_URL`.
