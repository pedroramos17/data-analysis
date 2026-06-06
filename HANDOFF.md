# Project Handoff

Date: 2026-06-04

Project: `github.com/pedroramos17/data-analysis`

Working directory:
`/home/pedro/dev/data-analysis`

## Current State

- Branch: `main`
- Remote status: PR #8 merged; working tree now has uncommitted Phase 3-18 plus
  RunPod pipeline Phase 0-2 and pipeline Phase 3-4 changes.
  hybrid MVP changes.
- Latest commit: `2e599d8 Merge pull request #8 from pedroramos17/codex/quant4-multifractal-refactor`
- Merged PR: `https://github.com/pedroramos17/data-analysis/pull/8`
- PR title: `[codex] Add Quant4 research cockpit and hybrid runtime foundation`
- Previous ai-memory handoff id: `019e87ac-7707-7e51-8665-92ca727ce99b`
- `agentmemory:session-history` returned no stored sessions for this project, so
  this file is based on current git state and the active chat context.

## Recent Commits

- `2e599d8 Merge pull request #8 from pedroramos17/codex/quant4-multifractal-refactor`
- `0c9dd30 Merge branch 'main' into codex/quant4-multifractal-refactor`
- `7de36e7 docs: add project handoff`
- `b36f513 feat: add cloud provider facade`
- `4b239f0 feat: add runtime mode settings`

## What Was Implemented

### Cookbook And Preview

- Added a local-first research cookbook covering QuantSpace, Quant4, MarketLab,
  graphs/topology, risk/regime, portfolio, LOB, full experiment, and
  multifractal systems.
- Added read-only Django preview at `/cookbook/`.
- Updated monitoring navigation and tests.

### Hybrid Quant MVP Phase 0

- Added `ARCHITECTURE_NOTES.md`.
- Added `MIGRATION_PLAN.md`.
- Added root `TODO.md`.
- Documented current SQLite, Parquet/Arrow, Quant4, QuantSpace, Sourceflow,
  monitoring, command, test, and optional dependency boundaries.

### Phase 1 Runtime Modes

- Added `src/config/settings.py`.
- Supports:
  - `APP_ENV=local | cloud | test`
  - `DEPLOYMENT_MODE=onprem | cloud_mvp | cloud_prod`
  - `DB_MODE=sqlite | postgres`
  - `OLAP_MODE=duckdb`
  - `STORAGE_PROVIDER=local | s3 | r2 | b2 | minio`
  - `QUEUE_PROVIDER=local | redis | sqs | rabbitmq`
  - `SECRETS_PROVIDER=env | aws_secrets | gcp_secret_manager | doppler`
  - `MODEL_PROVIDER=local | huggingface | s3 | r2`
  - `COMPUTE_PROVIDER=local | colab | vastai | gcp | aws`
- Wired `public_monitor/settings.py` through runtime settings while preserving
  SQLite as the local default.
- Updated `.env.example`.

### Phase 2 Provider Facade

- Added `src/providers/`.
- Added interfaces and local/cloud-boundary providers for:
  - storage,
  - database,
  - warehouse,
  - queue,
  - secrets,
  - compute,
  - model registry.
- Added `build_provider_registry()` and getters:
  - `get_storage()`
  - `get_db()`
  - `get_warehouse()`
  - `get_queue()`
  - `get_secrets()`
  - `get_model_registry()`
  - `get_compute()`
- Optional SDK imports are confined to provider implementations:
  - `boto3` in S3-compatible storage,
  - `redis` in Redis queue,
  - `psycopg` in Postgres database,
  - `duckdb` in DuckDB warehouse.

### Phase 3 Database Compatibility Layer

- Added `src/database/core_schema.py` with SQLAlchemy Core definitions for:
  - `assets`,
  - `market_bars`,
  - `lob_snapshots`,
  - `features`,
  - `signals`,
  - `backtest_runs`,
  - `risk_runs`,
  - `model_artifacts`,
  - `ingestion_runs`.
- Added `CompatibleJSON`, which compiles to Postgres JSONB and SQLite text JSON.
- Added `alembic.ini`, `alembic/env.py`, and revision `20260602_0001` using
  `metadata.create_all(checkfirst=True)` for idempotent MVP table creation.
- Added SQLite schema/idempotency tests and optional Postgres integration test
  gated by `POSTGRES_TEST_DATABASE_URL`.
- Added `docker-compose.postgres.yml` for optional local Postgres testing.
- Updated docs, dependencies, runtime database settings tests, and TODO phase
  numbering.

### Phase 4 DuckDB Analytical Layer

- Added `src/warehouse/`:
  - `duckdb_context.py` for DuckDB connections, local Parquet discovery, stable
    empty views, and object-store prefix mirroring into local cache.
  - `views.py` for `v_market_bars`, `v_returns`, `v_realized_volatility`,
    `v_multifractal_features`, `v_lob_features`, `v_model_predictions`,
    `v_signal_panel`, `v_backtest_panel`, and `v_risk_panel`.
  - `materialize.py` for `build_research_panel`, `build_training_dataset`,
    `build_backtest_dataset`, and `materialize_feature_store`.
- Added `src/cli.py` entrypoint for:
  `python -m src.cli warehouse build-panel --config configs/panel.yaml`.
- Added `configs/panel.yaml` and `docs/duckdb_warehouse.md`.
- Added `tests/test_warehouse.py`; the DuckDB/PyArrow local Parquet integration
  test auto-skips when those packages are not installed.
- Added `duckdb` and `PyYAML` to core requirements.

### Phase 5 Object Storage Facade

- Added `src/storage/`:
  - `paths.py` for raw data, Parquet datasets, model artifacts, backtest
    reports, risk reports, logs, and cached dataset object keys.
  - `manifest.py` for `_manifest.json` payloads with schema, row count, source,
    timestamp, content hash, path, URI, partition, and metadata.
  - `artifact_store.py` for provider-neutral writes through local or
    S3-compatible storage providers.
- Added `build_data_lake_store()` so callers can switch between local, S3, R2,
  B2, and MinIO via environment settings only.
- Improved S3-compatible listing pagination without assuming AWS-only behavior.
- Added `docs/object_storage.md` and `tests/test_storage_facade.py`.
- Added optional `boto3` to `requirements-cloud.txt`; business logic does not
  import it directly.

### Phase 6 Cheapest Cloud MVP Deployment

- Added `Dockerfile` with configurable `REQUIREMENTS_FILE` build arg:
  - local builds use `requirements.txt`,
  - cloud builds use `requirements-cloud.txt`.
- Added `docker-compose.local.yml` with app plus optional Postgres, MinIO, and
  Redis profiles.
- Added `docker-compose.cloud-mvp.yml` for one cheap VPS/free-tier VM with app,
  Postgres volume, optional MinIO, optional Redis, and scheduler profile.
- Added `.env.cloud.example`; updated `.env.example` with host/port/web worker
  defaults.
- Added `scripts/bootstrap_local.sh` and `scripts/bootstrap_cloud_mvp.sh`.
- Added `Makefile` targets: `local-up`, `cloud-mvp-up`, `migrate`,
  `ingest-sample`, `build-features`, `train-baseline`, `predict`, `backtest`,
  `risk`, and `smoke-test`.
- Added `/healthz/` and `/metrics/` via `monitoring.health_views`.
- Added `docs/deployment_mvp.md`; `.env` and `.env.cloud` are now ignored.

### Phase 7 Pre-trained Model Layer

- Added `src/models/`:
  - `base.py` for `BaseForecastModel`, `ForecastPrediction`, and model-layer
    errors.
  - `baselines.py` for naive return, pure-Python ridge, and optional
    LightGBM/XGBoost baselines.
  - `registry.py` for default model factory registration plus compatibility
    `model_artifacts` helpers.
  - `pretrained/` adapters for NeuralProphet, Chronos, PatchTST, and TimesFM;
    local JSON checkpoints run without remote downloads.
  - `sequence/` optional PyTorch placeholders for TCN, GRU-attention, Mamba,
    Fin-Mamba, and SAMBA.
  - `inference/` helpers for batch prediction, online prediction, Parquet
    output, and compatibility `signals` insertion.
- Added `docs/model_layer.md` and `tests/test_model_layer.py`.
- Fin-Mamba now implements a budget-friendly PyTorch architecture module with
  input projection, causal normalization, Mamba-style state-space placeholder,
  causal depthwise convolution, gated residual blocks, optional cross-asset and
  graph mixing, optional regime fusion, checkpoint save/load, and return,
  volatility, drawdown, regime-probability, and signal-confidence heads.
- SAMBA now implements a hybrid sequence architecture with local causal
  convolution, state-space/Mamba-style branch, low-rank attention branch, gated
  fusion, residual normalization, cross-asset context, forecast and uncertainty
  heads, and explainability diagnostics.

### Phase 8 Provider Control-Plane Hardening

- Tightened `LocalComputeProvider` so manifest-only specs return `PLANNED`
  instead of faking completed work.
- Local compute now runs an explicit callable supplied as `handler`, `runner`,
  or `callable`, records `COMPLETED` with the real result, and records `FAILED`
  with structured error metadata on exceptions.
- `BatchStubComputeProvider` remains manifest-only and returns `QUEUED` for
  future cloud/GPU execution.
- Added `src.providers.provenance.build_provider_provenance()` for non-secret
  provider metadata: app/deployment mode, database, storage, warehouse, queue,
  secrets, model registry, compute, and budget guards.
- Quant4 full experiment provenance now includes provider metadata under
  `Experiment.provenance_json["providers"]`; `FullExperimentConfig` can inject
  provider metadata for programmatic runs.
- Added dependency-light `tests/test_provider_facades.py` and a Django test
  assertion in `quant4/tests/test_full_experiment.py`.

### Phase 9 SAMBA Architecture Module

- Replaced `src/models/sequence/samba_block.py` placeholder with:
  - `SambaBlock` for one hybrid causal-conv/state-space/low-rank-attention
    block.
  - `SambaEncoder` for stacked blocks with input projection and optional
    cross-asset context.
  - `SambaForecastModel`, a `BaseForecastModel` wrapper with forecast and
    uncertainty heads.
- Registered SAMBA in `build_default_model_registry()` as `samba` and
  `samba_forecast`.
- Added branch diagnostics: contribution weights, feature saliency placeholder,
  temporal contribution summary, and optional cross-asset weights.
- Added `configs/samba.yaml` and `tests/test_samba.py`.

### Phase 10 Feature Store And Quant Modules

- Added `src/features/`:
  - `definitions.py` cataloging price/volume, LOB, multifractal, risk,
    portfolio, regime, and knowledge/graph feature groups.
  - `sql.py` generating DuckDB SQL over warehouse views into long-form feature
    rows.
  - `pipeline.py` materializing versioned Parquet outputs under
    `gold/features/version=<version>/feature_store.parquet`.
  - `metadata.py` aggregating long-form rows into the SQLite/Postgres
    compatibility `features` table.
- Added CLI command:
  `python -m src.cli features build --config configs/features.yaml`.
- Added `configs/feature_store.yaml`, `configs/features.yaml`,
  `docs/feature_pipeline.md`, and `tests/test_feature_pipeline.py`.

### Phase 11 API Facade

- Added `src/api/`:
  - `app.py` FastAPI app factory with OpenAPI docs.
  - `main.py` ASGI entrypoint for `uvicorn src.api.main:app`.
  - `handlers.py` provider-backed route behavior independent of FastAPI.
  - `jobs.py` queue/compute submission helper.
  - `repository.py` compatibility-table read helpers.
- Added endpoints for health, runtime config, ingest, feature builds, model
  train/predict, backtest/risk run manifests, assets, signals, backtest/risk
  lookup, models, and storage presign.
- Heavy jobs queue/plan by default; explicit `sync: true` runs small local
  handlers where implemented.
- Added `docs/api_facade.md` and `tests/test_api_facade.py`.
- Added FastAPI/Uvicorn to core requirements for OpenAPI support.

### Phase 12 CLI Commands

- Replaced `src/cli.py` with the full command tree:
  - `config show`
  - `db migrate`
  - `ingest run --config`
  - `features build --config`
  - `warehouse build-panel --config`
  - `model train --config`
  - `model predict --config`
  - `backtest run --config`
  - `risk run --config`
  - `storage sync --from local --to object`
  - `smoke-test`
- CLI calls provider registry directly, so every core MVP path can run without
  the API server.
- Added friendly missing cloud credential messages for object storage/Postgres.
- Added config examples: `configs/ingest.yaml`, `configs/features.yaml`,
  `configs/model.yaml`, `configs/predict.yaml`, `configs/backtest.yaml`, and
  `configs/risk.yaml`.
- Added `docs/cli.md` and `tests/test_cli.py`.

### Phase 13 MVP Demo Workflow

- Added the one-process MVP orchestrator in `src/workflows/mvp_demo.py` for:
  - deterministic sample OHLCV ingest,
  - raw Parquet writes through `DataLakeArtifactStore`,
  - SQLite/Postgres compatibility registration,
  - DuckDB research panel and feature-store materialization,
  - naive baseline training and provider-backed model artifact save,
  - optional Fin-Mamba/SAMBA architecture metadata,
  - batch prediction, Parquet export, and signal persistence,
  - backtest/risk report persistence and final report export.
- Added CLI command:
  `python -m src.cli mvp-demo --config configs/cloud_mvp.yaml`.
- Added `make mvp-demo` using `PYTHON?=python3`, keeping local development
  container-optional.
- Added MVP config examples:
  `configs/ingest_sample.yaml`, `configs/features_mvp.yaml`,
  `configs/model_baseline.yaml`, `configs/model_fin_mamba_small.yaml`,
  `configs/model_samba_small.yaml`, `configs/predict_mvp.yaml`,
  `configs/backtest_mvp.yaml`, `configs/risk_mvp.yaml`, and
  `configs/cloud_mvp.yaml`.
- Added `tests/test_mvp_demo.py` with dependency-light tests plus a full local
  integration test gated on SQLAlchemy, DuckDB, and PyArrow.
- Tightened signal persistence so `signal_row()` converts ISO timestamps to
  `datetime` before inserting into the compatibility `signals.ts` DateTime
  column.
- Updated `docs/cli.md` and `TODO.md` for the MVP demo entrypoint.

### Phase 14 Explainability And Diagnostics

- Added `src/models/explainability.py` with:
  - required signal explanation envelope fields,
  - batch prediction explanation enrichment,
  - sequence diagnostic JSON helpers,
  - dependency-free alpha validation metrics.
- `run_batch_prediction()` now enriches every prediction before Parquet export,
  SQL signal insertion, and API response serialization.
- Every signal explanation includes `model_name`, `model_version`,
  `feature_set_version`, `top_features`, `horizon`, `confidence`,
  `uncertainty_proxy`, `regime_context`, `risk_context`, and
  `data_quality_flags`.
- API synchronous model prediction responses include `explanation_json`; the
  compatibility `signals.explanation_json` column remains the API read path for
  persisted signals.
- SAMBA row predictions now include temporal contribution summaries, feature
  saliency placeholders, uncertainty proxy, and branch diagnostics.
- Fin-Mamba architecture/runtime diagnostics now expose temporal contribution,
  feature saliency, and latent-state summary hooks.
- MVP backtest reports now include alpha validation diagnostics: IC, rank IC,
  hit ratio, turnover, drawdown, Sharpe-like, Sortino-like, Calmar-like, Melao
  Index placeholder, existing-signal correlation, and regime-conditional
  performance.
- Added `tests/test_explainability.py` and expanded API/model/MVP tests for the
  explanation contract.
- Updated `docs/model_layer.md`, `docs/api_facade.md`, `docs/cli.md`, and
  `TODO.md`.

### Phase 15 Testing

- Added `tests/test_phase15_testing.py` covering:
  - settings parsing for local/cloud profiles and budget settings,
  - provider registry local resolution without cloud SDKs,
  - local storage round trip/listing/presign/path-safety,
  - SQLite provider health/migration contract,
  - optional Postgres provider boundary,
  - DuckDB query provider behavior with lazy missing-dependency failure,
  - model registry factories and local artifact provider,
  - feature calculation SQL contract,
  - PyTorch-gated Fin-Mamba and SAMBA forward passes,
  - local full MVP pipeline gated on SQLAlchemy, DuckDB, and PyArrow,
  - Docker Compose Postgres config smoke when Docker is available,
  - MinIO/object-storage round trip only when explicitly cloud-enabled,
  - `make -n smoke-test` and `make -n mvp-demo` smoke checks.
- Budget safety is encoded in tests: external Postgres and object-storage
  connectivity tests skip unless `ENABLE_CLOUD_TESTS=true`; the default test run
  does not call paid cloud services.
- Updated `TODO.md` with the Phase 15 testing checklist.

### Phase 16 Documentation

- Added architecture docs:
  - `docs/architecture/cloud_facade.md`,
  - `docs/architecture/database_modes.md`,
  - `docs/architecture/data_lake_duckdb.md`,
  - `docs/architecture/model_registry.md`,
  - `docs/architecture/cheap_cloud_mvp.md`.
- Added model docs:
  - `docs/models/fin_mamba.md`,
  - `docs/models/samba.md`.
- Added runbooks:
  - `docs/runbooks/local_mode.md`,
  - `docs/runbooks/cloud_mvp_mode.md`,
  - `docs/runbooks/recovery.md`.
- Added budget doc: `docs/cost/budget_plan.md`.
- Updated `README.md` with local setup, cloud MVP setup, key env vars, provider
  matrix, full MVP command, architecture diagram, data flow diagram, and model
  flow diagram.
- Updated `TODO.md` with the Phase 16 documentation checklist.

### Phase 17 Budget-First Architecture Rules

- Added `docs/architecture/budget_first_rules.md` with explicit MVP cheap-stack
  constraints, forbidden MVP infrastructure, future upgrade seams, enforcement
  rules, and acceptance criteria.
- Added `tests/test_phase17_budget_rules.py` to enforce dependency-light budget
  rules over runtime defaults, provider enum seams, Docker Compose service sets,
  GPU-disabled env examples, and README documentation links.
- Updated `README.md`, `TODO.md`, `ARCHITECTURE_NOTES.md`, `MIGRATION_PLAN.md`,
  `docs/architecture/cheap_cloud_mvp.md`, and `docs/cost/budget_plan.md` to
  point at the budget-first rule set.

### Phase 18 Final Deliverables

- Added `docs/final_deliverables.md` covering the required final handoff topics:
  changed-file summary, local mode, cloud MVP mode, MVP demo, Postgres,
  S3-compatible storage, SQLite retention, baseline train/predict,
  Fin-Mamba/SAMBA enablement, known limitations, and next recommended tasks.
- Added `tests/test_phase18_final_deliverables.py` to pin required sections,
  key commands/settings, README link, and the research-only/no-live-trading/no
  profitability-claim boundary.
- Updated `README.md`, `TODO.md`, `ARCHITECTURE_NOTES.md`, `MIGRATION_PLAN.md`,
  and this handoff with Phase 18 status.

### RunPod Pipeline Phase 0-2 And Pipeline Phase 3-4

- Added audit docs:
  `docs/audit/current_pipeline_map.md` and
  `docs/audit/gaps_for_cloud_pipeline.md`.
- Extended `src/config/settings.py` with `cloud_gpu`, `runpod`, `stub`, local/Redis
  queue, orchestrator, rate-limit provider, model device, cost mode, sliding
  window, autoscaling, efficiency, cost guard, and security settings.
- Added `src/providers/compute/runpod.py`, a dry-run-only RunPod facade that
  produces job specs and never launches paid infrastructure by default.
- Added `python -m src.cli gpu-job-dry-run` and `make gpu-job-dry-run`.
- Added `make mvp-demo-local` and made `make smoke-test` host-local and
  cloud-credential-free.
- Added `tests/test_phase1_runtime_modes.py`.
- Extended compute providers with `stream_logs`, `cancel_job`, `terminate_idle`,
  `estimate_cost`, and `healthcheck`.
- Added generic `src/providers/compute/dry_run.py` for `COMPUTE_PROVIDER=stub`;
  Colab/VastAI remain manifest-only batch stubs.
- Added `put_file`/`get_file` to storage providers.
- Added `ack`/`retry`/`dead_letter` to local and Redis queue providers.
- Added memory and Redis rate-limit providers and `ProviderRegistry.get_rate_limit()`.
- Added `tests/test_phase2_provider_facades.py` for dry-run compute, local file
  storage, queue retry/dead-letter, rate limiting, missing credential errors, and
  no direct RunPod SDK imports.
- Added `src/pipeline/ingestion/` with source abstractions, market/news/LOB
  local/mock sources, validation, timestamp normalization, dedupe, raw writes,
  and SQLite/Postgres ingestion metadata registration.
- Updated raw lake layout to
  `raw/source={source}/asset_type={asset_type}/symbol={symbol}/timeframe={timeframe}/date={YYYY-MM-DD}/part-000.parquet`.
- Extended `ingestion_runs` with explicit source, asset, timestamp, row count,
  dedupe, missing-ratio, URI, hash, timing, and `error_json` columns while
  preserving `stats_json`/`error` compatibility fields.
- Wired `python -m src.cli ingest run --config configs/ingest.yaml` to execute
  the local pipeline and added `python -m src.cli ingest validate --path ...`.
- Added `tests/test_phase3_ingestion_pipeline.py`.
- Added `src/pipeline/preprocessing/` with cleaner, aligner, normalizer,
  missing-value, outlier, corporate-action, and runner modules.
- Wired `python -m src.cli preprocess run --config configs/preprocess.yaml`.
- Preprocessing reads raw Parquet through DuckDB when available and uses a
  deterministic local/mock fallback for dependency-light ingestion files.
- Preprocessing writes `bronze/market_bars/part-000.parquet`,
  `silver/market_bars/part-000.parquet`, and
  `silver/market_bars/_quality_report.json` through the storage provider.
- Quality flags include `missing_ohlcv`, `stale_price`, `zero_volume`,
  `price_jump`, `invalid_spread`, `incomplete_lob`, `timezone_adjusted`, and
  `imputed`.
- Added `tests/test_phase4_preprocessing_pipeline.py`.
- Added `src/pipeline/features/` with base helpers and price/volume, LOB,
  multifractal, regime, risk, graph, and runner modules.
- Wired `python -m src.cli features build --config configs/features.yaml` to the
  Phase 5 feature runner while preserving CLI result keys like `rows`, `version`,
  `groups`, and `metadata_rows`.
- Feature outputs are partitioned as
  `features/feature_set={name}/version={version}/symbol={symbol}/timeframe={timeframe}/part-000.parquet`.
- Added `feature_runs` compatibility metadata table and Alembic revision
  `20260604_0003_feature_runs.py`.
- Feature extraction reports runtime seconds, memory MB, row throughput,
  no-future-leakage policy, input rows, output rows, and metadata rows.
- Added `tests/test_phase5_feature_pipeline.py`.

## Validation Already Run

Use `.venv-win`; the WSL `.venv` is not reliable in this checkout.

Commands run successfully during the latest phases:

```powershell
.\.venv-win\Scripts\ruff.exe check src monitoring\tests\test_provider_registry.py
.\.venv-win\Scripts\python.exe manage.py check
.\.venv-win\Scripts\python.exe manage.py makemigrations --check --dry-run
.\.venv-win\Scripts\python.exe manage.py test monitoring.tests.test_runtime_settings
.\.venv-win\Scripts\python.exe manage.py test monitoring.tests.test_provider_registry
.\.venv-win\Scripts\python.exe manage.py test quant4 quantspace
.\.venv-win\Scripts\python.exe manage.py test
```

Latest full suite result: `270 tests`, all passing.

Current-session validation in the Linux shell:

```bash
python3 -m py_compile src/database/__init__.py src/database/core_schema.py alembic/env.py alembic/versions/20260602_0001_core_mvp_schema.py quant4/tests/test_database_compat.py src/config/settings.py monitoring/tests/test_runtime_settings.py monitoring/tests/test_provider_registry.py
python3 -m py_compile src/warehouse/__init__.py src/warehouse/duckdb_context.py src/warehouse/views.py src/warehouse/materialize.py src/cli.py tests/test_warehouse.py
python3 -m unittest tests.test_warehouse
python3 -m py_compile src/storage/__init__.py src/storage/manifest.py src/storage/paths.py src/storage/artifact_store.py src/providers/storage/s3_compatible.py tests/test_storage_facade.py
python3 -m unittest tests.test_storage_facade tests.test_warehouse
python3 -m py_compile monitoring/health_views.py monitoring/urls.py
python3 -m py_compile src/models/__init__.py src/models/base.py src/models/baselines.py src/models/registry.py src/models/pretrained/__init__.py src/models/pretrained/timeseries_foundation.py src/models/pretrained/neuralprophet_adapter.py src/models/pretrained/chronos_adapter.py src/models/pretrained/patchtst_adapter.py src/models/pretrained/timesfm_adapter.py src/models/sequence/__init__.py src/models/sequence/_torch.py src/models/sequence/tcn.py src/models/sequence/gru_attention.py src/models/sequence/mamba_block.py src/models/sequence/fin_mamba.py src/models/sequence/samba_block.py src/models/inference/__init__.py src/models/inference/batch_predict.py src/models/inference/online_predict.py tests/test_model_layer.py
python3 -m unittest tests.test_model_layer
python3 -m compileall -q src/models/sequence/fin_mamba.py tests/test_fin_mamba.py
python3 -m unittest tests.test_fin_mamba tests.test_model_layer
python3 -m compileall -q src/models/sequence/samba_block.py src/models/registry.py src/models/sequence/__init__.py tests/test_samba.py
python3 -m unittest tests.test_samba tests.test_model_layer
python3 -m compileall -q src/features src/cli.py tests/test_feature_pipeline.py
python3 -m unittest tests.test_feature_pipeline tests.test_warehouse tests.test_model_layer
python3 -m compileall -q src/api tests/test_api_facade.py
python3 -m unittest tests.test_api_facade tests.test_feature_pipeline tests.test_model_layer
python3 -m compileall -q src/cli.py tests/test_cli.py
python3 -m unittest tests.test_cli tests.test_api_facade tests.test_feature_pipeline tests.test_model_layer
python3 -m compileall -q src/providers quant4/services/full_experiment.py tests/test_provider_facades.py quant4/tests/test_full_experiment.py
python3 -m unittest tests.test_provider_facades tests.test_model_layer tests.test_storage_facade tests.test_warehouse
make -n local-up cloud-mvp-up migrate ingest-sample build-features train-baseline predict backtest risk smoke-test
docker compose -f docker-compose.local.yml config
COMPOSE_PROFILES=minio,scheduler docker compose --env-file .env.cloud.example -f docker-compose.cloud-mvp.yml config
python3 -m src.cli --help
python3 -m compileall -q src/workflows src/cli.py src/models/inference/batch_predict.py tests/test_mvp_demo.py tests/test_model_layer.py
python3 -m unittest tests.test_mvp_demo
python3 -m unittest tests.test_cli tests.test_model_layer
make -n mvp-demo
python3 -m compileall -q src/models src/api src/workflows tests/test_explainability.py tests/test_model_layer.py tests/test_api_facade.py tests/test_mvp_demo.py
python3 -m unittest tests.test_explainability tests.test_model_layer
python3 -m unittest tests.test_api_facade tests.test_mvp_demo
python3 -m unittest tests.test_explainability tests.test_mvp_demo tests.test_cli tests.test_api_facade tests.test_feature_pipeline tests.test_samba tests.test_fin_mamba tests.test_model_layer tests.test_provider_facades tests.test_storage_facade tests.test_warehouse
python3 -m compileall -q tests/test_phase15_testing.py
python3 -m unittest tests.test_phase15_testing
python3 -m unittest tests.test_phase15_testing tests.test_explainability tests.test_mvp_demo tests.test_cli tests.test_api_facade tests.test_feature_pipeline tests.test_samba tests.test_fin_mamba tests.test_model_layer tests.test_provider_facades tests.test_storage_facade tests.test_warehouse
git diff --check
python3 -m compileall -q tests/test_phase17_budget_rules.py
python3 -m unittest tests.test_phase17_budget_rules
python3 -m unittest tests.test_phase17_budget_rules tests.test_phase15_testing tests.test_explainability tests.test_mvp_demo tests.test_cli tests.test_api_facade tests.test_feature_pipeline tests.test_samba tests.test_fin_mamba tests.test_model_layer tests.test_provider_facades tests.test_storage_facade tests.test_warehouse
python3 -m src.cli --help
git diff --check
python3 -m compileall -q tests/test_phase18_final_deliverables.py
python3 -m unittest tests.test_phase18_final_deliverables
python3 -m unittest tests.test_phase18_final_deliverables tests.test_phase17_budget_rules tests.test_phase15_testing tests.test_explainability tests.test_mvp_demo tests.test_cli tests.test_api_facade tests.test_feature_pipeline tests.test_samba tests.test_fin_mamba tests.test_model_layer tests.test_provider_facades tests.test_storage_facade tests.test_warehouse
python3 -m src.cli --help
git diff --check
python3 -m py_compile src/config/settings.py src/providers/provenance.py src/providers/registry.py src/providers/compute/runpod.py src/cli.py tests/test_phase1_runtime_modes.py monitoring/tests/test_runtime_settings.py tests/test_phase17_budget_rules.py
APP_ENV=local DEPLOYMENT_MODE=onprem DB_MODE=sqlite STORAGE_PROVIDER=local QUEUE_PROVIDER=local COMPUTE_PROVIDER=local MODEL_DEVICE=cpu python3 -m src.cli config show
APP_ENV=cloud DEPLOYMENT_MODE=cloud_gpu DB_MODE=sqlite STORAGE_PROVIDER=local QUEUE_PROVIDER=local COMPUTE_PROVIDER=runpod MODEL_DEVICE=cpu RUNPOD_DRY_RUN=true python3 -m src.cli gpu-job-dry-run --output /tmp/opencode/runpod_dry_run_phase1.json
python3 -m unittest tests.test_phase1_runtime_modes tests.test_phase17_budget_rules tests.test_provider_facades tests.test_cli
make -n smoke-test mvp-demo-local gpu-job-dry-run
make smoke-test
make gpu-job-dry-run
python3 -m unittest tests.test_phase1_runtime_modes tests.test_phase18_final_deliverables tests.test_phase17_budget_rules tests.test_phase15_testing tests.test_explainability tests.test_mvp_demo tests.test_cli tests.test_api_facade tests.test_feature_pipeline tests.test_samba tests.test_fin_mamba tests.test_model_layer tests.test_provider_facades tests.test_storage_facade tests.test_warehouse
python3 -m src.cli --help
git diff --check
```

All commands passed. `python3 -m unittest tests.test_storage_facade
tests.test_warehouse` ran 8 tests with the DuckDB/PyArrow integration test
skipped because dependencies are not installed in this shell.
`python3 -m unittest tests.test_model_layer` ran 9 dependency-light model tests.
`python3 -m unittest tests.test_provider_facades tests.test_model_layer
tests.test_storage_facade tests.test_warehouse` ran 24 tests with 1 expected
DuckDB/PyArrow skip after Phase 8 hardening.
`python3 -m unittest tests.test_fin_mamba tests.test_model_layer` ran 13 tests
with 4 PyTorch-gated Fin-Mamba runtime tests skipped because PyTorch is not
installed in this shell. `python3 -m unittest tests.test_samba
tests.test_model_layer` ran 16 tests with 4 PyTorch-gated SAMBA runtime tests
skipped. The final targeted lightweight suite ran 35 tests with 9 expected
skips. `python3 -m unittest tests.test_feature_pipeline tests.test_warehouse
tests.test_model_layer` ran 20 tests with 3 optional dependency skips for
SQLAlchemy and DuckDB/PyArrow-backed feature tests. The final targeted suite
`python3 -m unittest tests.test_feature_pipeline tests.test_samba
tests.test_fin_mamba tests.test_model_layer tests.test_provider_facades
tests.test_storage_facade tests.test_warehouse` ran 43 tests with 11 expected
optional dependency skips. Targeted Django tests are still blocked in this shell
because Django is not installed. `python3 -m unittest tests.test_api_facade
tests.test_feature_pipeline tests.test_model_layer` ran 22 tests with 3 optional
dependency skips, including FastAPI OpenAPI smoke when FastAPI is absent.
The final targeted suite `python3 -m unittest tests.test_api_facade
tests.test_feature_pipeline tests.test_samba tests.test_fin_mamba
tests.test_model_layer tests.test_provider_facades tests.test_storage_facade
tests.test_warehouse` ran 48 tests with 12 expected optional dependency skips.
`python3 -m unittest tests.test_cli tests.test_api_facade
tests.test_feature_pipeline tests.test_model_layer` ran 28 tests with 3 expected
optional dependency skips. The final targeted suite including CLI, API, feature,
sequence, model, provider, storage, and warehouse tests ran 54 tests with 12
expected optional dependency skips. SQLAlchemy, DuckDB, PyYAML, boto3, PyArrow, PyTorch,
FastAPI, and any real pretrained libraries need to be installed before running
the full dependency and provider-backed tests. Docker Compose config validation
passed for local and cloud MVP files, but image builds and service startup were
not run in this shell. `python3 -m unittest tests.test_mvp_demo` ran 4 tests
with the full MVP integration test skipped because SQLAlchemy, DuckDB, and
PyArrow are not installed in this shell. `python3 -m unittest tests.test_cli
tests.test_model_layer` ran 15 tests successfully after the Phase 13 CLI and
signal timestamp changes. Phase 14 validation added `python3 -m unittest
tests.test_explainability tests.test_model_layer`, which ran 12 tests
successfully, and `python3 -m unittest tests.test_api_facade tests.test_mvp_demo`,
which ran 10 tests with 2 expected optional dependency skips. The final Phase 14
targeted suite ran 62 tests with 13 expected optional dependency skips.
`python3 -m unittest tests.test_phase15_testing` ran 17 tests with 5 expected
skips for missing optional dependencies or disabled cloud gates. The final Phase
15 targeted regression suite ran 79 tests with 18 expected skips. Phase 16 docs
were verified by confirming the requested docs paths exist, `git diff --check`,
and `python3 -m src.cli --help`. Phase 17 validation added
`tests.test_phase17_budget_rules`, which ran 7 tests successfully. The final
Phase 17 targeted regression suite ran 86 tests with 18 expected optional
dependency skips, `python3 -m src.cli --help` loaded successfully, and
`git diff --check` passed. Phase 18 validation added
`tests.test_phase18_final_deliverables`, which ran 4 tests successfully. The
final Phase 18 targeted regression suite ran 90 tests with 18 expected optional
dependency skips, `python3 -m src.cli --help` loaded successfully, and
`git diff --check` passed. RunPod pipeline Phase 1 validation compiled runtime,
provider, CLI, and tests; `make smoke-test` passed with local SQLite/local
providers and no cloud credentials; `make gpu-job-dry-run` wrote
`exports/gpu_jobs/runpod_dry_run.json` with `launches_paid_infrastructure=false`;
the final broad lightweight regression suite ran 95 tests with 18 expected
optional dependency skips; `python3 -m src.cli --help` loaded successfully; and
`git diff --check` passed. RunPod pipeline Phase 2 validation added
`tests.test_phase2_provider_facades`, which ran 10 tests successfully. The
affected dependency-light suite ran 33 tests successfully. The final broad
lightweight regression suite ran 105 tests with 18 expected optional dependency
skips; `python3 -m src.cli --help` loaded successfully; and `git diff --check`
passed.
Phase 3 validation added `tests.test_phase3_ingestion_pipeline`, which ran 3
tests successfully. The affected ingestion/CLI/storage/API/schema suite ran 24
tests with 6 dependency-aware skips. The exact local CLI examples passed:
`python3 -m src.cli ingest run --config configs/ingest.yaml` and
`python3 -m src.cli ingest validate --path /tmp/opencode/phase3_lake/raw/source=sample`.
The final broad lightweight regression suite ran 108 tests with 18 expected
optional dependency skips.
Phase 4 validation added `tests.test_phase4_preprocessing_pipeline`, which ran 2
tests successfully. The affected preprocessing/ingestion/CLI/storage/warehouse/
feature suite ran 27 tests with 3 expected optional dependency skips. The
documented command passed in a temporary local data lake after mock ingest:
`python3 -m src.cli preprocess run --config configs/preprocess.yaml`.
Phase 5 validation added `tests.test_phase5_feature_pipeline`, which ran 2 tests
successfully. The affected feature/CLI/schema suite ran 21 tests with 7 expected
optional dependency skips. The documented ingest -> preprocess -> features flow
passed in a temporary local data lake using `python3 -m src.cli features build
--config configs/features.yaml`.

## Safety Boundaries

- Keep SQLite as the local/default metadata store.
- Keep Parquet/Arrow as the heavy analytical artifact boundary.
- Do not introduce required cloud credentials for local mode.
- Do not run cloud/Postgres/object-store connectivity tests unless
  `ENABLE_CLOUD_TESTS=true` is explicitly set.
- Do not hardcode cloud SDKs in business logic.
- Keep optional dependencies lazy and provider-contained.
- Do not add live trading, broker execution, paid API requirements, or managed
  GPU requirements.

## Next Steps

- Install/update dependencies in `.venv-win`, then run the full MVP demo:
  `python -m src.cli mvp-demo --config configs/cloud_mvp.yaml`.
- With SQLAlchemy installed, verify `GET /signals` returns persisted
  `explanation_json` rows from the compatibility DB.
- Run targeted database and warehouse compatibility tests after dependencies are
  installed.
- Run optional Postgres integration with `docker-compose.postgres.yml` only when
  Docker is available and `POSTGRES_TEST_DATABASE_URL` is set.
- Run the DuckDB local integration path with the updated requirements installed:
  `python -m unittest tests.test_warehouse`.
- Optional next smoke path: run MinIO locally and point `STORAGE_PROVIDER=minio`
  plus `OBJECT_STORAGE_ENDPOINT_URL` at it to validate real S3-compatible
  writes.
- Optional next deployment smoke path: run `scripts/bootstrap_local.sh`, then
  `make smoke-test` after dependencies/images are available.
- Optional next cloud hardening: real MinIO smoke coverage, VPS hardening notes,
  and dependency-backed provider tests.
- Optional next RunPod phase: implement signed job manifests, artifact staging,
  real RunPod launch/termination behind the compute provider, and cloud tests
  gated by `ENABLE_CLOUD_TESTS=true`.
- Optional next ingestion hardening: add licensed/provider-backed market data
  adapters behind `source_base.py`, apply rate limits per source, and add opt-in
  real Parquet validation tests when PyArrow is installed.
- Optional next preprocessing hardening: add exchange calendars, configured
  holiday sessions, real corporate-action fixtures, and DuckDB-backed integration
  tests when DuckDB/PyArrow are installed.
- Optional next feature hardening: add DuckDB SQL materialization tests for real
  Parquet, cross-asset graph/correlation features over larger universes, and
  persisted `feature_runs` checks against Postgres.
- Stage only current-task files and run `git diff --cached --check` before each
  commit.
- Note: `.github/workflows/opencode.yml` is untracked and unrelated to this
  database work unless the user says otherwise.
