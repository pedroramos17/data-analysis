# Cheapest Cloud MVP Deployment

The MVP deployment target is one cheap VPS or free-tier VM. It does not require
Kubernetes, managed GPU, a paid vector database, Kafka, or managed object
storage.

## Files

- `Dockerfile`
- `docker-compose.local.yml`
- `docker-compose.cloud-mvp.yml`
- `.env.example`
- `.env.cloud.example`
- `scripts/bootstrap_local.sh`
- `scripts/bootstrap_cloud_mvp.sh`
- `Makefile`

## Local Stack

```bash
make local-up
make migrate
make ingest-sample
make smoke-test
```

Local compose starts the app with SQLite by default. Optional profiles are
available for Postgres, MinIO, and Redis:

```bash
COMPOSE_PROFILES=postgres,minio,redis docker compose -f docker-compose.local.yml up -d
```

## Cloud MVP Stack

```bash
cp .env.cloud.example .env.cloud
# edit secrets and allowed hosts
CLOUD_ENV_FILE=.env.cloud make cloud-mvp-up
CLOUD_ENV_FILE=.env.cloud make migrate
```

The default cloud compose runs:

- app container with Gunicorn,
- Postgres container with a durable volume,
- optional MinIO profile for S3-compatible object storage,
- optional scheduler profile using a simple shell sleep loop,
- optional Redis profile if queue needs outgrow local mode.

For managed/free Postgres, replace `DATABASE_URL` in `.env.cloud` and use a
small compose override to remove the bundled `postgres` dependency. For R2, B2,
AWS S3, or external MinIO, set `STORAGE_PROVIDER`, `OBJECT_STORAGE_BUCKET`,
`OBJECT_STORAGE_ENDPOINT_URL`, and object-storage credentials in `.env.cloud`.

DuckDB stores local cache state in the app data volume and can be rebuilt from
Parquet/object storage. Models can live in object storage or `/app/models`.

## Make Targets

- `make local-up`
- `make cloud-mvp-up`
- `make migrate`
- `make ingest-sample`
- `make build-features`
- `make train-baseline`
- `make predict`
- `make backtest`
- `make risk`
- `make smoke-test`

## Health And Metrics

- `/healthz/` returns JSON health and database status.
- `/metrics/` returns a minimal Prometheus-compatible gauge.

Structured logs are emitted to stdout/stderr by Django/Gunicorn and should be
collected by the VPS runtime, Docker logs, or a cheap log shipper.
