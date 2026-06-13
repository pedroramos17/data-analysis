# Hybrid Quant MVP TODO

Status: Phase 5 feature extraction pipeline implemented

## Phase 0: Audit And Preservation

- [x] Map current Django database layer and SQLite default.
- [x] Map SQLite helpers, feature flag overrides, and model metadata tables.
- [x] Map Parquet/Arrow artifact writers and local data lake directories.
- [x] Map ingestion, feature engineering, model, backtest, and CLI surfaces.
- [x] Confirm DuckDB, Postgres, object storage, queue, secrets, and cloud model
  registry are not yet implemented as provider facades.
- [x] Confirm no Dockerfile, compose file, or GitHub Actions workflow is
  present.
- [x] Document preservation rules in `ARCHITECTURE_NOTES.md`.
- [x] Document additive migration path in `MIGRATION_PLAN.md`.

## Phase 1: Provider Settings And Local Facades

- [x] Add provider-neutral deployment settings with `local` as the default.
- [x] Add local fallback interfaces for database, storage, analytics, compute,
  queue, secrets, and model registry.
- [x] Add tests that every provider category resolves locally without optional
  cloud dependencies.
- [x] Document environment variables and local fallback behavior.

## Phase 2: Database Profiles

- [x] Keep SQLite as the default Django database profile.
- [x] Add optional Postgres profile rendering from environment variables or
  `DATABASE_URL`.
- [x] Add clear missing-driver errors for selected Postgres mode.
- [x] Add tests for SQLite default and optional Postgres config.

## Phase 3: Database Compatibility Layer

- [x] Preserve existing Django migrations and SQLite local workflow.
- [x] Add SQLAlchemy Core compatibility schema for SQLite and Postgres.
- [x] Add Alembic migration scaffold for the MVP core tables.
- [x] Add text-JSON fallback for SQLite and JSONB support for Postgres.
- [x] Add SQLite schema/idempotency tests.
- [x] Add optional Docker Compose Postgres integration test path.

## Phase 4: DuckDB Analytics Over Parquet

- [x] Add optional DuckDB analytics provider over existing Parquet artifacts.
- [x] Preserve existing PyArrow write/read paths.
- [x] Add fallback behavior when DuckDB is missing.
- [x] Add tests with local Parquet fixtures.
- [x] Add warehouse CLI for research panel materialization.

## Phase 5: Object Storage Facade

- [x] Add local filesystem storage provider.
- [x] Add optional S3-compatible provider interface for MinIO, Cloudflare R2,
  Backblaze B2, and AWS S3.
- [x] Keep bucket, endpoint, key, and region values in settings/secrets.
- [x] Add fake-provider and local-provider tests.
- [x] Add data lake path helpers for raw data, Parquet datasets, model
  artifacts, reports, logs, and cached datasets.
- [x] Add `_manifest.json` writes with schema, row count, source, timestamp,
  and content hash.

## Phase 6: Cheapest Cloud MVP Deployment

- [x] Add `Dockerfile` for app container builds.
- [x] Add `docker-compose.local.yml` with app and optional Postgres, MinIO, and
  Redis profiles.
- [x] Add `docker-compose.cloud-mvp.yml` for one cheap VPS or free-tier VM.
- [x] Add `.env.cloud.example` and keep local `.env.example` defaults.
- [x] Add bootstrap scripts for local and cloud MVP startup.
- [x] Add Makefile targets for setup, migrations, sample ingest, features,
  baseline training, prediction dataset, backtest, risk, and smoke tests.
- [x] Add `/healthz/` and optional `/metrics/` endpoints.
- [x] Keep Kubernetes, managed GPU, paid vector DB, and Kafka out of the MVP.

## Phase 7: Pre-trained Model Layer

- [x] Add stable `BaseForecastModel` interface.
- [x] Add CPU-first naive and ridge return baselines.
- [x] Add optional LightGBM/XGBoost baseline boundaries.
- [x] Add local-checkpoint pretrained adapters for NeuralProphet, Chronos,
  PatchTST, and TimesFM.
- [x] Add optional PyTorch TCN and GRU-attention placeholders.
- [x] Add Fin-Mamba architecture with state-space, causal-conv, gated-mixing,
  cross-asset, regime, projection, and head components.
- [x] Add Fin-Mamba return, volatility, drawdown, regime, and confidence heads.
- [x] Add batch and online inference helpers.
- [x] Add model artifact and signal persistence helpers for SQLite/Postgres
  compatibility tables.
- [x] Keep GPU and pretrained libraries optional.

## Phase 8: Compute, Queue, Secrets, And Model Registry

- [x] Add local synchronous compute provider.
- [x] Keep manifest-only local jobs `PLANNED` unless a callable actually runs.
- [x] Add no-op or in-memory local queue provider.
- [x] Add environment-backed local secrets provider.
- [x] Add local/object-store/Hugging Face boundary model registry providers.
- [x] Record non-secret provider metadata in Quant4 experiment provenance.
- [x] Add tests that compute and batch stubs do not fake completed metrics.

## Phase 9: SAMBA Architecture Module

- [x] Add local causal convolution branch.
- [x] Add state-space/Mamba-style branch.
- [x] Add sparse or low-rank attention branch.
- [x] Add gated fusion and residual normalization.
- [x] Add branch contribution, feature saliency, and temporal contribution
  diagnostics.
- [x] Expose `SambaBlock`, `SambaEncoder`, and `SambaForecastModel`.
- [x] Register SAMBA as `samba` and `samba_forecast` in the default model
  registry.
- [x] Add SAMBA tests and YAML config example.

## Phase 10: Feature Store And Quant Modules

- [x] Add DuckDB/Parquet feature-store SQL pipeline.
- [x] Add price/volume feature group.
- [x] Add LOB feature group with quote/depth proxies and placeholders where raw
  quote columns are unavailable.
- [x] Add multifractal proxy feature group.
- [x] Add risk feature group.
- [x] Add portfolio baseline/constraint/cost feature group.
- [x] Add regime feature group.
- [x] Add knowledge/graph placeholder feature group.
- [x] Write versioned feature outputs under `gold/features/version=...`.
- [x] Add optional SQLite/Postgres compatibility metadata persistence.
- [x] Add CLI, config, docs, and tests.

## Phase 11: API Facade

- [x] Add FastAPI app factory and ASGI entrypoint.
- [x] Add `GET /health` and `GET /config/runtime`.
- [x] Add job endpoints for ingest, features, models, backtests, and risk.
- [x] Add read endpoints for assets, signals, backtests, risk, models, and
  storage presigning.
- [x] Route API calls through provider registry.
- [x] Keep routes storage-provider and database-provider neutral.
- [x] Queue/plan heavy jobs by default and allow synchronous small MVP runs.
- [x] Add OpenAPI smoke tests and handler smoke tests.

## Phase 12: CLI Commands

- [x] Add `config show`.
- [x] Add `db migrate`.
- [x] Add `ingest run --config`.
- [x] Add `features build --config`.
- [x] Preserve `warehouse build-panel --config`.
- [x] Add `model train --config` and `model predict --config`.
- [x] Add `backtest run --config` and `risk run --config`.
- [x] Add `storage sync --from local --to object`.
- [x] Add `smoke-test`.
- [x] Add clear missing object-storage/Postgres credential messages.
- [x] Add config examples and CLI smoke tests.

## Phase 13: MVP Demo Workflow And Budget-First Cloud Hardening

- [x] Add `python -m src.cli mvp-demo --config configs/cloud_mvp.yaml`.
- [x] Add `make mvp-demo` as the one-command MVP pipeline entrypoint.
- [x] Add deterministic sample ingest, raw Parquet, compatibility DB, DuckDB
  panel/features, baseline train, batch prediction, signals, backtest, risk, and
  report export workflow.
- [x] Add MVP configs for sample ingest, features, baseline model, optional
  Fin-Mamba/SAMBA metadata, prediction, backtest, risk, and cloud MVP demo.
- [x] Keep local development container-optional.
- [ ] Run the full dependency-backed MVP demo after SQLAlchemy, DuckDB, PyArrow,
  and PyYAML are installed.
- [ ] Add optional MinIO smoke path for local object-storage testing.
- [x] Add budget guard settings and dry-run examples.
- [x] Add validation commands for local and cheap-cloud profiles.

## Phase 14: Explainability And Diagnostics

- [x] Add required `explanation_json` envelope for every batch prediction signal.
- [x] Include model name/version, feature-store version, top features, horizon,
  confidence, uncertainty proxy, regime/risk context, and data-quality flags.
- [x] Add SAMBA branch diagnostics, temporal contribution summary, and feature
  saliency placeholder to sequence prediction explanations.
- [x] Add Fin-Mamba temporal contribution, feature saliency, and latent-state
  summary diagnostics.
- [x] Add dependency-free alpha validation metrics: IC, rank IC, hit ratio,
  turnover, drawdown, Sharpe-like, Sortino-like, Calmar-like, Melao placeholder,
  existing-signal correlation, and regime-conditional performance.
- [x] Ensure API prediction responses include `explanation_json`.
- [ ] Verify persisted `GET /signals` explanation payload with SQLAlchemy-backed
  local database after dependencies are installed.

## Phase 15: Testing

- [x] Add dependency-light unit coverage for settings parsing, provider registry,
  local storage, SQLite provider, optional Postgres provider boundary, DuckDB
  query boundary, model registry, and feature SQL calculations.
- [x] Add PyTorch-gated Fin-Mamba and SAMBA forward-pass tests.
- [x] Add local full MVP pipeline integration test gated on SQLAlchemy, DuckDB,
  and PyArrow.
- [x] Add Docker Compose Postgres config smoke when Docker is available.
- [x] Add MinIO/object-storage integration test gated on `ENABLE_CLOUD_TESTS=true`
  plus object storage endpoint/bucket/credentials.
- [x] Add `make -n smoke-test` and `make -n mvp-demo` smoke tests.
- [x] Ensure cloud/Postgres/object-store connectivity tests do not run unless
  `ENABLE_CLOUD_TESTS=true`.

## Phase 16: Documentation

- [x] Add architecture docs for cloud facade, database modes, data lake/DuckDB,
  model registry, and cheap cloud MVP.
- [x] Add model docs for Fin-Mamba and SAMBA.
- [x] Add runbooks for local mode, cloud MVP mode, and recovery.
- [x] Add cost/budget plan.
- [x] Update README with local setup, cloud MVP setup, environment variables,
  provider matrix, full MVP command, and Mermaid diagrams.

## Phase 17: Budget-First Architecture Rules

- [x] Add explicit cheap-stack rules for one VPS/free-tier VM, Docker Compose,
  Postgres, DuckDB, S3-compatible storage, CPU inference, and optional GPU only
  for batch training.
- [x] Document the out-of-MVP-scope components: Kubernetes, Kafka, Spark,
  managed vector DB, always-on GPU, expensive observability, and live trading.
- [x] Document the future upgrade path from local providers to managed or batch
  providers without changing MVP defaults.
- [x] Add dependency-light tests that enforce cheap runtime defaults, provider
  upgrade seams, Docker Compose service boundaries, GPU-disabled env examples,
  cloud-test gates, and README documentation links.

## Phase 18: Final Deliverables

- [x] Add final deliverables document covering changed files, local mode, cloud
  MVP mode, MVP demo, Postgres, S3-compatible storage, SQLite retention,
  baseline train/predict, Fin-Mamba/SAMBA enablement, known limitations, and
  next recommended tasks.
- [x] Keep the final deliverables research-only with no trading profitability
  claim and no live trading execution path.
- [x] Add dependency-light tests for the final deliverables document and README
  link.

## RunPod Pipeline Phase 0: Audit

- [x] Add `docs/audit/current_pipeline_map.md` mapping ingestion,
  preprocessing, features, training, validation, backtest/risk, SQLite,
  DuckDB/Parquet, CLI/API, Docker, orchestration, and bottlenecks.
- [x] Add `docs/audit/gaps_for_cloud_pipeline.md` identifying provider injection
  points and cloud GPU gaps before refactors.

## RunPod Pipeline Phase 1: Runtime Modes And Budget Settings

- [x] Add unified runtime settings for `cloud_gpu`, RunPod, local/Redis queue,
  orchestrator, rate-limit provider, model device, and cost mode.
- [x] Add `PipelineSettings`, `SlidingWindowSettings`, `RunPodSettings`,
  `AutoscalingSettings`, `RateLimitSettings`, `EfficiencySettings`,
  `CostGuardSettings`, and `SecuritySettings`.
- [x] Keep budget-first defaults: SQLite, local storage, DuckDB, CPU, local
  orchestration, memory rate limiting, no Redis, no GPU, no paid APIs, and no
  cloud tests.
- [x] Add RunPod dry-run compute facade and CLI/Make target that writes a job
  spec without launching paid infrastructure.

## RunPod Pipeline Phase 2: Provider Facades And Contracts

- [x] Extend compute providers with log streaming, `cancel_job`, idle
  termination, cost estimation, and health checks.
- [x] Add generic `stub` dry-run compute provider and keep Colab/VastAI as
  manifest-only batch stubs.
- [x] Add provider-neutral storage file transfer methods: `put_file` and
  `get_file`.
- [x] Add queue acknowledgement, retry, and dead-letter methods for local and
  Redis queue boundaries.
- [x] Add memory and Redis rate-limit providers behind `ProviderRegistry`.
- [x] Add dependency-light tests for local defaults, dry-run behavior, explicit
  missing credential errors, and no direct RunPod SDK imports.

## Phase 3: Data Ingestion Pipeline

- [x] Add `src/pipeline/ingestion/` with source abstractions, market/news/LOB
  local/mock sources, validators, and runner.
- [x] Implement discover, fetch, schema validation, UTC timestamp normalization,
  deduplication, raw partition writes, and ingestion metadata registration.
- [x] Use the requested raw lake layout under
  `raw/source={source}/asset_type={asset_type}/symbol={symbol}/timeframe={timeframe}/date={YYYY-MM-DD}/part-000.parquet`.
- [x] Extend `ingestion_runs` with explicit source, asset, timestamp, row-count,
  dedupe, missing-ratio, URI, hash, timing, and `error_json` columns while
  preserving existing compatibility columns.
- [x] Add `python -m src.cli ingest validate --path ...`.
- [x] Add dependency-light tests for repeatability, dedupe safety, validation, CLI
  run/validate, and failed-run error metadata.

## Phase 4: Preprocessing Pipeline

- [x] Add `src/pipeline/preprocessing/` with cleaner, aligner, normalizer,
  missing-value, outlier, corporate-action, and runner modules.
- [x] Implement raw reads through DuckDB when available with deterministic local
  fallback for mock ingestion files.
- [x] Clean names/types, normalize UTC timestamps, sort, deduplicate, handle
  missing bars, align daily calendars, optionally apply corporate actions, detect
  outliers, and emit quality flags.
- [x] Save bronze and silver Parquet-compatible outputs under `data/lake/bronze/`
  and `data/lake/silver/` through the storage provider.
- [x] Emit a deterministic `_quality_report.json` with quality flag counts,
  timestamp alignment policy, inserted calendar rows, hashes, and no-future-
  leakage metadata.
- [x] Add `python -m src.cli preprocess run --config configs/preprocess.yaml`.
- [x] Add dependency-light tests for determinism, quality flags, explicit
  timestamp/calendar alignment, and CLI execution.

## Phase 5: Feature Extraction Pipeline

- [x] Add `src/pipeline/features/` with base helpers and price/volume, LOB,
  multifractal, regime, risk, graph, and runner modules.
- [x] Read bronze/silver Parquet through DuckDB when available, with deterministic
  local fallback for dependency-light mock files and no pandas dependency.
- [x] Implement versioned feature-set outputs under
  `features/feature_set={name}/version={version}/symbol={symbol}/timeframe={timeframe}/part-000.parquet`.
- [x] Add `feature_runs` metadata table with config, rows, columns, timing,
  status, output URI, and `error_json`.
- [x] Ensure rolling windows use only past/current rows ordered by
  symbol/timeframe/timestamp and report `no_future_leakage=true`.
- [x] Report runtime seconds, memory MB, row throughput, input rows, output rows,
  and metadata rows from `python -m src.cli features build --config configs/features.yaml`.
- [x] Add dependency-light tests for versioned outputs, feature values, metadata,
  no-leakage policy, runtime metrics, and CLI execution.

## Always-On Constraints

- [ ] Do not delete SQLite mode.
- [ ] Do not break existing migrations.
- [ ] Do not hardcode cloud SDKs into business logic.
- [ ] Do not add required paid APIs or managed GPU dependencies.
- [ ] Keep every cloud component backed by a local fallback.
- [ ] Keep no-live-trading and no-fake-metrics boundaries explicit.
