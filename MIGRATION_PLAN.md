# Hybrid Quant MVP Migration Plan

Status: RunPod pipeline Phase 1 runtime settings implemented; dependency-backed MVP demo next

Date: 2026-06-02

## Goal

Move the existing offline-first quant research platform toward a cheap
cloud-ready MVP while preserving local SQLite mode and the current Django,
Quant, QuantSpace, Sourceflow, Parquet, and command structure.

The migration should be additive. Local users must be able to run the project
without Postgres, DuckDB, object storage, cloud queues, cloud secrets, or paid
GPU services.

## Phase 1: Provider Settings And Local Facades

Add a provider-neutral configuration layer with local defaults.

Planned behavior:

- `DEPLOYMENT_MODE=local` remains the default.
- Supported modes are `local`, `cheap_cloud_mvp`, and `production_ready`.
- Provider choices are expressed as names, not SDK objects.
- Required MVP facades:
  - database provider,
  - object storage provider,
  - analytics provider,
  - compute provider,
  - queue provider,
  - secrets provider,
  - model registry provider.
- Local implementations use SQLite, local filesystem paths, optional DuckDB
  only when installed, synchronous compute, environment secrets, and local
  model artifact directories.

Implementation notes:

- Prefer a small owned settings module first. If Pydantic is introduced, keep
  it optional or lightweight and do not require it for local Django startup
  unless dependency policy is updated.
- Keep provider interfaces under Quant or a shared project namespace that
  existing apps can import without circular dependencies.
- Add tests that every provider category resolves to a local fallback.

## Phase 2: Database Profiles

Keep SQLite as the default transactional metadata database and add Postgres as
an optional profile.

Planned behavior:

- Local profile uses the existing `DATABASES["default"]` SQLite config.
- Cloud profile can build a Django Postgres config from environment variables
  or `DATABASE_URL`.
- Existing migrations remain unchanged and must run on SQLite.
- Postgres dependency is optional; missing driver should fail clearly only when
  the Postgres profile is selected.

Implementation notes:

- Do not replace Django ORM or existing Django migrations for web-app tables;
  any SQLAlchemy/Alembic schema must be additive.
- Add a configuration helper, not business-logic conditionals.
- Add tests for SQLite default, Postgres config rendering, and missing driver
  error messaging.

Implementation status:

- SQLite remains the default Django database profile.
- Optional Postgres profile rendering supports `DATABASE_URL` or split
  `POSTGRES_DB`, `POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_HOST`,
  `POSTGRES_PORT`, and `POSTGRES_SSLMODE` values.
- `psycopg` stays optional and is only imported inside the selected Postgres
  provider boundary.

## Phase 3: Database Compatibility Layer

The cloud MVP now includes an additive SQLAlchemy/Alembic compatibility schema
for core quant tables while preserving Django migrations as the web app's
authoritative migration path.

Implemented behavior:

- Existing SQLite mode and Django migrations are unchanged.
- SQLAlchemy Core table definitions live in `src.database.core_schema`.
- Alembic migration `20260602_0001` creates the MVP tables idempotently with
  `checkfirst=True`.
- SQLite stores compatibility JSON fields as text JSON.
- Postgres compiles those JSON fields as JSONB.
- Optional Docker Compose Postgres testing is available through
  `docker-compose.postgres.yml` and `POSTGRES_TEST_DATABASE_URL`.

Core MVP tables:

- `assets`
- `market_bars`
- `lob_snapshots`
- `features`
- `signals`
- `backtest_runs`
- `risk_runs`
- `model_artifacts`
- `ingestion_runs`

## Phase 4: DuckDB Analytics Over Parquet

Add an analytical facade that can query existing Parquet artifacts through
DuckDB when installed, while retaining PyArrow read/write paths.

Planned behavior:

- Local default remains PyArrow/Parquet artifact reads.
- DuckDB is optional and selected through the analytics provider.
- Missing DuckDB produces a clear dependency message and falls back to existing
  readers when the caller permits fallback.
- Query inputs are artifact URIs or local paths from existing metadata models.

Implementation notes:

- Do not rewrite existing Parquet writers.
- Add a small DuckDB adapter around existing artifact roots.
- Keep SQL templates simple and local; no external warehouse dependency.

Implementation status:

- `src.warehouse.duckdb_context` manages DuckDB connections, local Parquet
  globs, and object-store partition mirroring into a local cache.
- `src.warehouse.views` registers stable views for market bars, returns,
  realized volatility, multifractal features, LOB features, predictions,
  signals, backtests, and risk.
- `src.warehouse.materialize` builds research, training, backtest, and feature
  store datasets directly from DuckDB SQL into Parquet.
- `python -m src.cli warehouse build-panel --config configs/panel.yaml` is the
  local CLI entrypoint.

## Phase 5: Object Storage Facade

Introduce storage providers without changing research modules to vendor SDKs.

Planned behavior:

- Local filesystem provider is default.
- Optional S3-compatible provider supports MinIO, Cloudflare R2, Backblaze B2,
  and AWS S3 through the same interface.
- Artifact metadata stores provider-neutral URIs and provenance.
- Existing local path strings remain valid.
- Missing optional SDK fails clearly only when the S3-compatible provider is
  selected.

Implementation notes:

- Use a project-owned interface with operations such as `put_file`, `get_file`,
  `exists`, `list`, and `uri_for`.
- Keep bucket names, endpoints, keys, and regions in settings/secrets, not
  business logic.
- Add tests using a fake storage provider and the local filesystem provider.

Implementation status:

- `src.storage.DataLakeArtifactStore` writes data lake objects and manifests
  through the configured storage provider.
- `src.storage.DataLakePaths` defines provider-neutral keys for raw data,
  Parquet datasets, model artifacts, backtest reports, risk reports, logs, and
  cached datasets.
- Dataset and artifact saves write `_manifest.json` with schema, row count,
  source, creation time, content hash, path, URI, partition, and metadata.
- `build_data_lake_store()` builds the facade from runtime environment settings,
  so local and S3-compatible targets use the same business code.
- `boto3` is optional and imported only in the S3-compatible provider boundary.

## Phase 6: Cheapest Cloud MVP Deployment

Add deployment scaffolding for one cheap VPS or free-tier VM without requiring
Kubernetes, managed GPU, paid vector databases, or Kafka.

Implemented behavior:

- `Dockerfile` builds the app with core or cloud requirements.
- `docker-compose.local.yml` starts the app with SQLite and optional Postgres,
  MinIO, and Redis profiles.
- `docker-compose.cloud-mvp.yml` runs app, Postgres volume, optional MinIO,
  optional Redis, and a simple scheduler profile on one VM.
- `.env.cloud.example` documents cloud MVP Postgres, object storage, DuckDB,
  model, queue, and budget settings.
- `scripts/bootstrap_local.sh` and `scripts/bootstrap_cloud_mvp.sh` bootstrap
  migrations and compatibility migrations.
- `Makefile` provides local/cloud setup, migration, ingest, feature, train,
  prediction, backtest, risk, and smoke-test targets.
- `/healthz/` and `/metrics/` support cheap container health and optional
  Prometheus-style scraping.

## Phase 7: Pre-trained Model Layer

Add architecture hooks for financial time-series models without making GPU
training required.

Planned behavior:

- Register model specs for SAMBA, Mamba, and Fin-Mamba as optional Quant model
  components.
- CPU-first inference path accepts pre-trained local or object-storage artifact
  references.
- Missing Torch or architecture packages fail clearly.
- Optional GPU batch execution is represented as a job manifest for Colab,
  Vast.ai, GCP, or AWS, not as a managed GPU dependency.
- Results must state that no predictive performance is claimed without
  walk-forward evaluation.

Implementation notes:

- Start with model spec objects and validation hooks.
- Keep architecture packages optional behind feature flags.
- Store inference runs in `ModelRun` with artifact URIs, config hash, random
  seed, data range, split range, and provenance.

Implementation status:

- `src.models.base` defines `BaseForecastModel` and `ForecastPrediction`.
- `src.models.baselines` provides CPU-first naive and pure-Python ridge
  baselines plus optional LightGBM/XGBoost boundaries.
- `src.models.pretrained` provides local-checkpoint adapters for NeuralProphet,
  Chronos, PatchTST, and TimesFM with clear missing-checkpoint errors.
- `src.models.sequence` provides optional PyTorch TCN, GRU-attention, Mamba,
  Fin-Mamba, and SAMBA modules.
- `src.models.inference` supports batch and online prediction, Parquet output,
  and compatibility `signals` table insertion.
- `src.models.registry` registers model factories and compatibility
  `model_artifacts` records.

## Phase 8: Compute, Queue, Secrets, And Model Registry Facades

Add cheap-cloud-ready control-plane abstractions while retaining local sync
execution.

Planned behavior:

- Compute provider supports local synchronous execution and future batch job
  manifests.
- Queue provider supports local no-op/in-memory behavior for MVP tests.
- Secrets provider reads environment variables locally and can later wrap cloud
  secret stores.
- Quant full-experiment DAG can include provider metadata in experiment
  provenance without changing safety rules.

Implementation notes:

- Reuse `quant.services.registry`, `Experiment`, `ModelRun`, `PipelineJob`,
  and compute profile conventions where possible.
- Do not add live trading, account access, or broker execution paths.
- Add tests that compute and queue providers never fake completed metrics.

Implementation status:

- `LocalComputeProvider` runs an explicit local callable synchronously and
  records `COMPLETED` or `FAILED` from real execution.
- Manifest-only local compute specs are recorded as `PLANNED`, not fake
  completed work.
- `BatchStubComputeProvider` records future cloud/GPU manifests as `QUEUED`.
- `LocalQueueProvider` provides an in-memory publish/consume boundary for tests
  and local MVP workflows.
- `EnvSecretProvider` keeps secrets behind an injectable environment boundary.
- Local and object-store model registries provide artifact metadata boundaries;
  Hugging Face remains a clear optional-dependency stub.
- `build_provider_provenance()` records provider choices and budget guards
  without connection strings, access keys, or secret values.
- `quant.services.full_experiment` stores provider provenance under
  `Experiment.provenance_json["providers"]` while preserving no-live-trading
  behavior.

## Phase 9: SAMBA Architecture Module

Implement a CPU-safe SAMBA-style hybrid sequence module for long, noisy
financial time series and cross-asset context.

Implemented behavior:

- `SambaBlock` combines local causal convolution, a selective state-space
  placeholder, and strided low-rank attention.
- `SambaEncoder` stacks SAMBA blocks behind an input projection and optional
  cross-asset context mixer.
- `SambaForecastModel` wraps the encoder with forecast and uncertainty heads and
  implements `BaseForecastModel` for model-registry use.
- The default forecast model registry exposes `samba` and `samba_forecast`.
- Diagnostics include branch contribution weights, feature saliency placeholder,
  temporal contribution summary, and optional cross-asset weights.
- `configs/samba.yaml` documents a CPU-safe example configuration.

## Phase 10: Feature Store And Quant Modules

Build a cheap cloud-ready feature pipeline over DuckDB/Parquet while retaining
SQLite/Postgres metadata compatibility.

Implemented behavior:

- `src.features.definitions` owns the feature catalog for price/volume, LOB,
  multifractal, risk, portfolio, regime, and knowledge/graph groups.
- `src.features.sql.feature_store_sql()` generates long-form feature rows from
  DuckDB warehouse views without pandas materialization.
- `src.features.pipeline.build_feature_store()` materializes versioned Parquet
  outputs under `gold/features/version=<version>/feature_store.parquet`.
- `src.features.metadata.persist_feature_metadata()` can aggregate long-form
  rows into the SQLite/Postgres compatibility `features` table.
- `python -m src.cli features build --config configs/features.yaml`
  is the CLI entrypoint.
- `docs/feature_pipeline.md` documents the groups, CLI, output layout, and
  metadata persistence.

## Phase 11: API Facade

Expose a provider-neutral HTTP facade over local and cheap-cloud workflows.

Implemented behavior:

- `src.api.app.create_app()` builds a FastAPI app with OpenAPI docs.
- `src.api.handlers` owns provider-backed route behavior independent of
  FastAPI, making it easy to smoke-test without an ASGI server.
- API calls use `ProviderRegistry` for database, storage, queue, compute, and
  model registry access.
- Heavy operations are queued/planned by default through queue and compute
  providers; explicit `sync: true` runs small local handlers where implemented.
- Storage presigning goes through the configured storage provider.
- Compatibility reads for assets, signals, backtests, and risk runs go through a
  repository helper rather than route-level SQLite/Postgres branching.

## Phase 12: CLI Commands

Expose core MVP workflows without requiring the API server.

Implemented behavior:

- `python -m src.cli config show` prints non-secret runtime provider metadata.
- `python -m src.cli db migrate` runs provider migration metadata and the
  additive compatibility schema when SQLAlchemy is installed.
- Ingest, backtest, and risk commands submit provider-backed job manifests.
- Feature and warehouse commands invoke DuckDB/Parquet materializers.
- Model train/predict commands run small synchronous baseline workflows by
  default from config files.
- Storage sync copies provider-neutral object keys between local storage and the
  configured object storage provider.
- `smoke-test` validates runtime, DB, queue, storage, and model registry names.
- Missing cloud credentials and optional SDK errors are rewritten into actionable
  CLI messages.

## Phase 13: Budget-First Cloud Hardening

Add deployment scaffolding after provider facades exist.

Planned behavior:

- Local development remains container-optional.
- Cheap cloud MVP can use Postgres plus object storage plus CPU web/worker
  process.
- GPU work remains external batch-only and manually approved.
- Deployment docs include estimated cost boundaries and disabled-by-default
  paid services.

Implementation notes:

- Add Docker/compose only after local provider tests pass.
- Include MinIO as the local object-storage smoke target if needed.
- Add explicit budget guard settings and dry-run command examples.

Implementation status:

- Docker Compose is the only MVP orchestrator.
- The default MVP stack remains Postgres, DuckDB, S3-compatible storage, local
  queue/planned jobs, local model registry, and CPU inference.
- GPU remains disabled by default and allowed only as an optional batch-training
  provider path.
- `docs/architecture/budget_first_rules.md` documents forbidden MVP components
  and the future upgrade path.
- Dependency-light tests assert the MVP does not require Kubernetes, Kafka,
  Spark, managed vector DB, always-on GPU, or expensive observability.

## Rollback Strategy

- Keep SQLite profile untouched and default.
- Keep all new cloud settings optional.
- Keep provider integrations behind feature flags or explicit provider
  selection.
- Revert provider modules independently without touching existing research
  commands.
- Validate rollback with `manage.py check`, `manage.py test quant researchspace`,
  and `manage.py test`.

## Acceptance Criteria

- Local mode still works without Postgres, DuckDB, boto, Torch, or cloud
  credentials.
- Existing migrations remain SQLite-compatible.
- Business logic depends on provider interfaces, not vendor SDKs.
- Analytical outputs remain Parquet-first.
- Cloud profile can be configured without deleting or mutating local SQLite
  mode.
- Optional dependencies fail clearly when selected and missing.
- No live trading or paid managed GPU dependency is introduced.
- Budget-first tests keep the MVP cheap while preserving upgrade seams.
