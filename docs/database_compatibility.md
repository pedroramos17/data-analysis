# Database Compatibility Layer

The project keeps the existing Django migrations and SQLite development flow.
The Quant MVP compatibility schema is additive and lives in SQLAlchemy/Alembic
under `src.database.core_schema` and `alembic/`.

## Local SQLite

```powershell
python manage.py migrate
alembic -c alembic.ini upgrade head
python manage.py test quant.tests.test_database_compat
```

SQLite stores compatibility JSON columns as text JSON. Existing `.sqlite` and
`.db` file strategies are unchanged; set `SQLITE_PATH` to choose the local file.

## Postgres

Install optional cloud dependencies, then run Django and compatibility
migrations against the same Postgres database:

```powershell
python -m pip install -r requirements-cloud.txt
$env:DB_MODE = "postgres"
$env:DATABASE_URL = "postgresql://quant:quant@localhost:54329/quant"
python manage.py migrate
alembic -c alembic.ini upgrade head
```

The Alembic environment normalizes `postgresql://` and `postgres://` URLs to
SQLAlchemy's `postgresql+psycopg://` driver form.

## Optional Docker Integration Test

```powershell
docker compose -f docker-compose.postgres.yml up -d postgres
$env:POSTGRES_TEST_DATABASE_URL = "postgresql+psycopg://quant:quant@localhost:54329/quant"
python manage.py test quant.tests.test_database_compat
docker compose -f docker-compose.postgres.yml down
```

The integration test creates a temporary Postgres schema and drops it at the end
of the test, leaving existing tables untouched.

## Core Tables

- `assets`
- `market_bars`
- `lob_snapshots`
- `features`
- `signals`
- `backtest_runs`
- `risk_runs`
- `model_artifacts`
- `ingestion_runs`

Shared queries should use SQLAlchemy Core expressions or Django ORM APIs. Avoid
raw SQL that depends on SQLite-only syntax.
