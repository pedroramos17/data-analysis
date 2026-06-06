# Current Pipeline Map

This audit captures the repository state before Phase 1 runtime-setting changes.
It should be updated when new provider boundaries are introduced.

## Existing Data Flow

The repository has two active pipeline layers:

| Layer | Current flow |
| --- | --- |
| Django/Quant4/Sourceflow | Management commands ingest public/financial data, normalize it into Django/SQLite metadata, export Parquet artifacts, compute Quant4 features/windows/risk/backtests, and record run metadata in Django models. |
| Provider-neutral MVP stack | `src.cli` and `src.api` use provider facades to ingest sample data, write raw Parquet, build DuckDB panels/features, train CPU baselines, persist predictions/signals, run backtest/risk reports, and export reports. |

The current MVP path is:

1. `python -m src.cli mvp-demo --config configs/cloud_mvp.yaml`
2. `src.workflows.mvp_demo.run_mvp_demo()` creates deterministic OHLCV rows.
3. `src.storage.DataLakeArtifactStore` writes raw Parquet and report artifacts.
4. `src.database.core_schema` compatibility tables register assets, ingestion runs,
   model artifacts, signals, backtests, and risk runs when SQLAlchemy is present.
5. `src.warehouse.DuckDBWarehouseContext` registers Parquet-backed views.
6. `src.features.pipeline.build_feature_store()` materializes long-form features.
7. `src.models.baselines` trains CPU-first baseline models.
8. `src.models.inference.batch_predict` writes predictions and `explanation_json`.
9. Backtest/risk reports are written to storage and optional DB tables.

## Ingestion Surfaces

- `monitoring/management/commands/ingest_*.py` for public-source, RSS, EDGAR,
  FRED, CFTC, market-data, and due-source ingestion.
- `monitoring/ingestion_v2.py` for normalized event/market records.
- `sourceflow/finance_ingestion/` for local files, official API connectors,
  public-web policy validation, normalization, quality checks, global market
  windows, and Parquet export.
- `quant4/management/commands/quant4_ingest_prices.py` and
  `quant4_ingest_lob.py` for Quant4 market and LOB imports.
- `src.workflows.mvp_demo.sample_market_rows()` for deterministic demo data.

## Preprocessing And Feature Extraction

- `sourceflow/finance_dataset/` builds leakage-controlled prediction rows,
  targets, manifests, and walk-forward splits.
- `sourceflow/finance_features/` builds multifractal and graph-style finance
  features.
- `quant4/services/multifractal/` contains MF-DFA/MF-DMA/MF-DCCA, wavelet,
  regime, risk, portfolio, and Parquet helpers.
- `quant4/services/lob/` handles LOB parsing, normalization, queue features,
  order-book features, labels, DeepLOB stubs, and LOB backtests.
- `quant4/services/marketlab/windows.py` provides rolling, expanding, and purged
  walk-forward windows with embargo metadata.
- `src/features/` builds the provider-neutral DuckDB feature store.
- `src/warehouse/` builds DuckDB views and materialized panels from Parquet.

## Model Training And Prediction

- `src/models/base.py` defines the forecast model interface.
- `src/models/baselines.py` provides CPU-first naive/ridge baselines and optional
  boosted baselines.
- `src/models/sequence/` contains optional PyTorch Fin-Mamba, SAMBA, TCN,
  GRU-attention, and Mamba blocks.
- `src/models/pretrained/` contains local-checkpoint adapters with no default
  remote downloads.
- `src/api/handlers.py` exposes sync local train/predict for small jobs and
  queue/compute manifests for heavier work.
- `sourceflow/finance_models/` contains older baseline, evaluation, XAI, and
  training-manifest helpers.

## Validation, Backtest, Risk, And Portfolio

- `sourceflow/finance_dataset/splits.py` provides walk-forward and purged
  embargo split helpers.
- `sourceflow/finance_models/evaluation.py` provides MSE and IC metrics.
- `src.models.explainability.alpha_validation_metrics()` provides dependency-light
  alpha diagnostics for MVP reports.
- `src.workflows.mvp_demo` contains the MVP backtest/risk report path.
- `quant4/services/marketlab/backtest.py`, `quant4/services/risk/`, and
  `quant4/services/portfolio/` provide older research services.
- `quant4/services/full_experiment.py` orchestrates a safe local DAG and enforces
  no-live-trading behavior.

## SQLite Usage

SQLite is the default local/on-prem metadata store and must remain in place.

- `public_monitor/settings.py` builds Django `DATABASES["default"]` from
  `src.config.settings`, defaulting to SQLite.
- `monitoring.models`, `monitoring.finance_models`, `monitoring.dashboard_models`,
  `monitoring.orchestration_models`, `quant4.models`, and `quantspace.models`
  are Django/SQLite-backed metadata surfaces.
- `monitoring.sqlite` and `monitoring.sqlite_retry` provide local SQLite behavior
  and retry helpers.
- `src.database.core_schema` provides additive SQLite/Postgres compatibility
  tables without replacing Django migrations.

## DuckDB And Parquet Usage

- `src.warehouse.duckdb_context` scans partitioned Parquet through DuckDB without
  pandas materialization for core MVP paths.
- `src.warehouse.materialize` writes research, training, backtest, and feature
  datasets directly to Parquet.
- `src.storage.artifact_store` writes raw data, model artifacts, reports, logs,
  cached datasets, and manifests through storage providers.
- `sourceflow.finance_ingestion.parquet_export` and
  `quant4.services.multifractal.data.parquet_store` are older PyArrow-based
  local Parquet writers/readers.

## Config, Env, Docker, CLI, API, And Orchestration

- Runtime settings live in `src/config/settings.py` and are consumed by Django,
  CLI, API, and provider registry code.
- Local env defaults live in `.env.example`; cloud MVP defaults live in
  `.env.cloud.example`.
- Docker setup uses `Dockerfile`, `docker-compose.local.yml`,
  `docker-compose.cloud-mvp.yml`, and `docker-compose.postgres.yml`.
- CLI entrypoint is `src/cli.py`.
- API entrypoint is `src/api/main.py` / `src/api/app.py`.
- Existing local orchestration lives in `monitoring/orchestration/` with
  SQLite-backed `PipelineJob`, `JobRunEvent`, `ResourceLock`, and worker heartbeat
  models.
- Existing cloud planning lives in `monitoring/cloud/` as provider-neutral
  manifests only; it does not launch provider SDK calls.

## Current Performance Bottlenecks

- `quant4.services.multifractal.data.parquet_store` reads all matching Parquet
  files into Python lists before filtering.
- `sourceflow.finance_ingestion.connectors.local_files` reads full CSV/JSONL and
  Parquet files into memory.
- `src.warehouse.duckdb_context` uses glob scans over Parquet directories; this is
  acceptable for MVP but should get partition manifests for large lakes.
- `src.models.inference.batch_predict` materializes predictions in memory before
  optional Parquet/DB writes.
- `monitoring.fetchers.rate_limit` is process-local; multi-worker/cloud mode needs
  a provider-backed rate limiter.

## Untouched Modules

These should remain local-first and should not be refactored during runtime-mode
settings work:

- Django migrations and current Django models.
- Existing SQLite retry and local dashboard worker behavior.
- Quant4 research services and no-live-trading guard.
- Sourceflow ingestion compliance and public-web permission checks.
- Existing Parquet artifact contracts.
