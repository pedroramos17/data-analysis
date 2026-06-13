# Final Deliverables

This MVP is for research, forecasting, risk, backtesting, and portfolio analytics
only. It does not claim trading profitability and does not include live trading,
broker connectivity, order placement, or execution adapters.

## 1. Summary Of Changed Files

Major changed or added areas:

| Area | Files |
| --- | --- |
| Runtime settings | `src/config/settings.py`, `.env.example`, `.env.cloud.example` |
| Provider facades | `src/providers/`, `src/providers/provenance.py` |
| Database compatibility | `src/database/core_schema.py`, `alembic.ini`, `alembic/` |
| Warehouse | `src/warehouse/` |
| Object storage | `src/storage/` |
| Feature store | `src/features/`, `configs/features*.yaml` |
| Model layer | `src/models/`, `configs/model*.yaml`, `configs/samba.yaml` |
| API facade | `src/api/` |
| CLI and workflows | `src/cli.py`, `src/workflows/mvp_demo.py`, `configs/cloud_mvp.yaml` |
| Deployment | `Dockerfile`, `docker-compose.local.yml`, `docker-compose.cloud-mvp.yml`, `docker-compose.postgres.yml`, `Makefile`, `scripts/` |
| Documentation | `README.md`, `ARCHITECTURE_NOTES.md`, `MIGRATION_PLAN.md`, `docs/` |
| Tests | `tests/test_*`, `monitoring/tests/test_runtime_settings.py`, `monitoring/tests/test_provider_registry.py`, `quant4/tests/test_*` |

## 2. How To Run Local Mode

Local mode is the default. It uses SQLite, local filesystem storage, DuckDB, a
local model registry, local queue/planned jobs, and CPU/local compute.

```bash
python3 -m venv .venv
source .venv/bin/activate
python3 -m pip install -r requirements.txt
python3 manage.py migrate
python3 -m src.cli db migrate
python3 -m src.cli config show
python3 -m src.cli smoke-test
```

On Windows PowerShell, activate with `.\.venv\Scripts\Activate.ps1` instead of
`source .venv/bin/activate`.

## 3. How To Run Cloud MVP Mode

Cloud MVP mode targets one cheap VPS or free-tier VM with Docker Compose,
Postgres, embedded DuckDB, S3-compatible storage, and CPU inference by default.

```bash
cp .env.cloud.example .env.cloud
# edit secrets, allowed hosts, storage endpoint, and budget settings
CLOUD_ENV_FILE=.env.cloud make cloud-mvp-up
CLOUD_ENV_FILE=.env.cloud make migrate
```

For direct CLI validation outside the Compose app container, load the env file
into the shell first:

```bash
set -a
source .env.cloud
set +a
python3 -m src.cli config show
python3 -m src.cli smoke-test
```

Optional profiles:

```bash
COMPOSE_PROFILES=minio,scheduler CLOUD_ENV_FILE=.env.cloud make cloud-mvp-up
COMPOSE_PROFILES=minio,redis,scheduler CLOUD_ENV_FILE=.env.cloud make cloud-mvp-up
```

## 4. How To Run The MVP Demo

The one-command demo runs sample ingest, raw Parquet writes, compatibility DB
registration, DuckDB panel/features, baseline training, optional sequence-model
metadata, batch prediction, signal persistence, backtest, risk, alpha diagnostics,
and report export.

```bash
python3 -m src.cli mvp-demo --config configs/cloud_mvp.yaml
```

Equivalent Make target:

```bash
make mvp-demo
```

CPU-forced local mode:

```bash
make mvp-demo-local
```

The full demo needs the dependency-backed stack from `requirements.txt`, including
SQLAlchemy, DuckDB, PyArrow, and PyYAML.

## 5. How To Configure Postgres

Set Postgres mode with a full URL:

```text
APP_ENV=cloud
DEPLOYMENT_MODE=cloud_mvp
DB_MODE=postgres
DATABASE_URL=postgresql://quant:<set-postgres-password>@postgres:5432/quant
```

Or use split variables:

```text
DB_MODE=postgres
POSTGRES_DB=quant
POSTGRES_USER=quant
POSTGRES_PASSWORD=<set-postgres-password>
POSTGRES_HOST=postgres
POSTGRES_PORT=5432
POSTGRES_SSLMODE=
```

Run migrations after changing the DB target:

```bash
python3 manage.py migrate
python3 -m src.cli db migrate
```

SQLite remains the Django local default; the SQLAlchemy/Alembic compatibility
schema is additive.

## 6. How To Configure S3-Compatible Storage

Use one of `minio`, `s3`, `r2`, or `b2`:

```text
STORAGE_PROVIDER=minio
DATA_LAKE_ROOT=/app/data/lake
OBJECT_STORAGE_BUCKET=quant-lake
OBJECT_STORAGE_ENDPOINT_URL=http://minio:9000
OBJECT_STORAGE_ACCESS_KEY_ID=minioadmin
OBJECT_STORAGE_SECRET_ACCESS_KEY=<set-object-storage-secret>
OBJECT_STORAGE_REGION=auto
```

For AWS S3, `OBJECT_STORAGE_ENDPOINT_URL` can be empty. For R2, B2, and MinIO,
set the provider endpoint URL. Business logic should keep using the storage
facade; optional SDK imports stay inside provider implementations.

Validate object storage settings with:

```bash
python3 -m src.cli config show
python3 -m src.cli storage sync --from local --to object --prefix raw/
```

Cloud/object-store connectivity tests must remain disabled unless explicitly run
with `ENABLE_CLOUD_TESTS=true`.

## 7. How To Keep SQLite Mode

Keep or set these local values:

```text
APP_ENV=local
DEPLOYMENT_MODE=onprem
DB_MODE=sqlite
SQLITE_PATH=./db.sqlite3
STORAGE_PROVIDER=local
DATA_LAKE_ROOT=./data/lake
QUEUE_PROVIDER=local
MODEL_PROVIDER=local
COMPUTE_PROVIDER=local
GPU_REQUIRED=false
GPU_BATCH_ENABLED=false
```

Do not set `DATABASE_URL` for local SQLite mode. Run the same app, API, and CLI
commands; provider settings select the local implementations.

## 8. How To Train/Predict With Baseline

Dependency-light baseline examples:

```bash
python3 -m src.cli model train --config configs/model.yaml
python3 -m src.cli model predict --config configs/predict.yaml
```

MVP baseline artifact/prediction examples:

```bash
python3 -m src.cli model train --config configs/model_baseline.yaml
python3 -m src.cli model predict --config configs/predict_mvp.yaml
```

`configs/predict_mvp.yaml` writes Parquet predictions and therefore needs PyArrow
installed. Persisted predictions include an `explanation_json` envelope when a DB
URL is configured.

## 9. How To Enable Fin-Mamba/SAMBA Models

Fin-Mamba and SAMBA are optional PyTorch sequence architecture paths. Keep them
CPU-first unless intentionally running approved batch training.

```text
COMPUTE_PROVIDER=local
GPU_REQUIRED=false
GPU_BATCH_ENABLED=false
```

Install PyTorch in the environment, then keep the optional sequence list in
`configs/cloud_mvp.yaml`:

```yaml
optional_sequence_models:
  - fin_mamba_small
  - samba_small
```

Run:

```bash
python3 -m src.cli mvp-demo --config configs/cloud_mvp.yaml
```

If PyTorch is unavailable, the MVP demo records those optional sequence steps as
skipped. Current Fin-Mamba/SAMBA support covers architecture modules, diagnostics,
registry/metadata hooks, and smoke paths; production training loops and validated
checkpoints remain future work.

## 10. Known Limitations

- No live trading, broker connectivity, order placement, or execution adapters.
- No trading profitability, investment advice, causal validity, or performance
  guarantee is claimed.
- Full MVP execution needs optional dependencies installed in the active Python
  environment.
- Cloud connectivity tests are intentionally gated by `ENABLE_CLOUD_TESTS=true`.
- Fin-Mamba/SAMBA training is not productionized; current support is
  architecture, diagnostics, metadata, and smoke validation.
- Pretrained adapters require local checkpoints; remote downloads are disabled by
  default.
- API persistence checks for `GET /signals` need a SQLAlchemy-backed compatibility
  DB in the running environment.
- Docker Compose config has been validated, but image builds and live service
  startup still need environment-specific smoke runs.
- RunPod support is dry-run/manifest-only; it does not launch GPU pods yet.

## 11. Next Recommended Implementation Tasks

- Install dependencies in the target environment and run the full MVP demo.
- Verify persisted `GET /signals` returns `explanation_json` from SQLite and
  Postgres compatibility DBs.
- Add optional MinIO integration smoke behind `ENABLE_CLOUD_TESTS=true`.
- Add backup/restore runbooks for Postgres volumes and object storage buckets.
- Add scheduler hardening and retry metadata for ingestion and feature jobs.
- Add baseline walk-forward evaluation reports over real licensed/local data.
- Add explicit model-training loops for Fin-Mamba/SAMBA with local checkpoints,
  reproducible seeds, and artifact provenance.
- Add CI jobs for dependency-light tests and opt-in dependency-backed smoke tests.
