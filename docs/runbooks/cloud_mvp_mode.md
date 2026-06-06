# Cloud MVP Mode Runbook

Cloud MVP mode is for one cheap VPS or free-tier VM with Postgres and optional
S3-compatible object storage.

## Setup

```bash
cp .env.cloud.example .env.cloud
# edit secrets, allowed hosts, storage endpoint, and budget settings
CLOUD_ENV_FILE=.env.cloud make cloud-mvp-up
CLOUD_ENV_FILE=.env.cloud make migrate
```

## Required Environment

```text
APP_ENV=cloud
DEPLOYMENT_MODE=cloud_mvp
DB_MODE=postgres
DATABASE_URL=postgresql://user:password@postgres:5432/quant
STORAGE_PROVIDER=minio
OBJECT_STORAGE_BUCKET=quant-lake
OBJECT_STORAGE_ENDPOINT_URL=http://minio:9000
OBJECT_STORAGE_ACCESS_KEY_ID=...
OBJECT_STORAGE_SECRET_ACCESS_KEY=...
```

## Optional Profiles

```bash
COMPOSE_PROFILES=minio,scheduler CLOUD_ENV_FILE=.env.cloud make cloud-mvp-up
COMPOSE_PROFILES=minio,redis,scheduler CLOUD_ENV_FILE=.env.cloud make cloud-mvp-up
```

## Validation

```bash
python -m src.cli config show
python -m src.cli smoke-test
python -m src.cli mvp-demo --config configs/cloud_mvp.yaml
```

Run cloud connectivity tests only when intentionally enabled:

```bash
ENABLE_CLOUD_TESTS=true python -m unittest tests.test_phase15_testing
```

Do not set `ENABLE_CLOUD_TESTS=true` in routine local CI.
