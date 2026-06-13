# Recovery Runbook

The MVP is designed so metadata, object storage, and DuckDB cache can be
recovered independently.

## SQLite Local Recovery

1. Stop the app or local workers.
2. Copy `db.sqlite3` to a timestamped backup.
3. Restore from the last known-good backup if needed.
4. Run `python manage.py migrate`.
5. Run `python -m src.cli db migrate` for compatibility tables.

## Postgres Recovery

1. Stop app writes or put the app in maintenance mode.
2. Use provider backups or `pg_dump`/`pg_restore` for self-hosted Postgres.
3. Re-run Django migrations and compatibility migrations.
4. Validate with `python -m src.cli smoke-test`.

## Data Lake Recovery

Object storage or local `DATA_LAKE_ROOT` is the durable analytical artifact
store. Restore the affected prefixes, then rebuild DuckDB cache and gold outputs:

```bash
python -m src.cli warehouse build-panel --config configs/panel.yaml
python -m src.cli features build --config configs/features.yaml
```

## DuckDB Recovery

DuckDB is a rebuildable cache over Parquet. If `analytics.duckdb` is corrupt or
stale, stop jobs, remove the file, and rebuild materializations from Parquet.

## Model Artifact Recovery

Restore `MODEL_CACHE_DIR` or object-store `models/` prefixes. Then confirm:

```bash
python -m src.cli smoke-test
python -m src.cli model train --config configs/model.yaml
```

## Incident Notes

Record the run id, affected providers, object prefixes, database backup id, and
commands used for recovery. Do not rotate cloud credentials into committed files.
