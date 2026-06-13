# Hybrid Quant MVP Architecture Notes

Status: RunPod pipeline Phase 1 runtime settings implemented

Date: 2026-06-02

## Current System Map

This repository is a local-first Django quant and public-source research system.
The current backend is Python/Django, with operational metadata in SQLite and
heavy analytical outputs written as Arrow/Parquet artifacts.

### Database Layer

- `public_monitor/settings.py` configures Django's default database as SQLite:
  `django.db.backends.sqlite3`, `BASE_DIR / "db.sqlite3"`, and a 30-second
  timeout.
- `monitoring.sqlite` registers SQLite pragmas for local dashboard workflows.
- `monitoring.sqlite_retry` wraps dashboard writes that may hit local SQLite
  lock contention.
- Django ORM models are the migration-backed metadata layer for monitoring,
  Quant, and QuantSpace.
- Sourceflow feature flags also support SQLite overrides through
  `monitoring.finance_models.FeatureFlagSetting`.

SQLite must remain the default local/offline profile. Future Postgres support
should be introduced as an alternate Django database profile, not as a
replacement for existing migrations.

### Metadata Models

- `monitoring.models` imports the public-source, dashboard, operational, and
  finance model modules.
- `monitoring.operational_models.ExportArtifact` records Parquet export
  metadata.
- `monitoring.finance_models` stores financial instruments, macro data,
  CFTC/fundamental records, multifractal features, statistical scores, and
  prediction dataset manifests.
- `quant.models` owns shared Quant metadata:
  `Asset`, `MarketDataset`, `Experiment`, `WindowArtifact`,
  `FeatureArtifact`, `RegimeRun`, `RiskRun`, `LOBRun`, `GraphSnapshot`,
  `PortfolioRun`, `ModelRun`, `BacktestRun`, and `ExplainabilityReport`.
- `researchspace.models` owns local paper, chunk, artifact, question, citation,
  extraction, and factor-candidate metadata.

The cloud MVP should keep these schemas compatible. New cloud/provider metadata
should be additive and migration-safe.

### Parquet and Data Lake Usage

Existing analytical storage is local-path based:

- `monitoring.exporters.ArrowTableWriter` writes document exports to Parquet.
- `sourceflow.finance_ingestion.parquet_export` writes finance rows through a
  thin PyArrow boundary.
- `researchspace.services.chunk_export` writes local paper chunks to Parquet.
- `quant.services.multifractal.data.parquet_store` writes partitioned OHLCV
  bars and return datasets.
- `quant.services.multifractal.features.feature_store` writes feature matrices
  to Parquet.
- Local artifact roots include `exports/`, `media/`, `data/`, and
  command-specific output directories.

DuckDB is available through `src.warehouse` as an embedded OLAP engine over
existing local or mirrored Parquet roots.

### Ingestion Modules

Current ingestion is command-driven and local-first:

- Monitoring ingestion handles RSS/HTML/API records through
  `monitoring.ingestion`, `monitoring.ingestion_v2`, fetchers, parsers,
  normalizers, and storage helpers.
- Sourceflow finance ingestion includes local files, SEC EDGAR, FRED, CFTC
  COT, Yahoo research, public web policy gates, normalization, quality checks,
  and global market windows.
- Quant ingestion commands include asset registration, price ingestion, LOB
  ingestion, multifractal CSV bar import, return generation, and full
  experiment orchestration.
- QuantSpace ingestion handles local PDF upload and paper chunking.

Cloud ingestion should wrap storage, secrets, and queues behind providers. It
must not place cloud SDK calls in these business modules.

### Feature Engineering and Research Modules

Quant already contains local CPU-first research modules:

- Core data foundation, calendars, corporate actions, futures rolls, FX
  normalization, windows, labels, leakage checks, feature store, factor store,
  evaluation, and reports.
- MarketLab under `quant/services/marketlab/` for windowing, shuffling, TDA,
  signatures, decomposition, graphs, contrastive workflows, benchmarks, and
  experimental backtests.
- Graph and topology lab under `quant/services/graphs/`.
- Risk and regime services under `quant/services/risk/`.
- Portfolio services under `quant/services/portfolio/`.
- LOB and microstructure services under `quant/services/lob/`.
- Multifractal services under `quant/services/multifractal/`.

These modules should remain local-first. Cloud execution should provide
artifact locations and job handles, not duplicate research code.

### Model Training and Inference

Current model support is intentionally light:

- `quant.services.registry` registers components by category and feature flag.
- `quant.services.full_experiment` plans a safe DAG with optional dependency
  skips for Torch, Torch Geometric, CVXPY, signature, RQA, and graph extras.
- `quant.services.lob.deeplob` contains local baselines and optional
  PyTorch-gated DeepLOB/TCN-LOB stubs.
- `quant.services.multifractal.ml.baselines` uses a deterministic majority
  fallback and optional scikit-learn baselines.
- `sourceflow.finance_models.mci_gru_gnn_spec` documents feature-flagged
  MCI-GRU/GNN architecture specs.

Fin-Mamba and SAMBA now live under `src.models.sequence` as optional PyTorch
modules. SAMBA exposes `SambaBlock`, `SambaEncoder`, and a registry-backed
`SambaForecastModel` with CPU-safe defaults and branch diagnostics. GPU batch
jobs should be provider-backed and optional, never a paid managed GPU
requirement.

### Backtest and Portfolio Surfaces

- Quant portfolio optimization stores `PortfolioRun` metadata and artifact
  paths for weights, trades, metrics, and risk reports.
- MarketLab has experimental backtest services under
  `quant/services/marketlab/backtest.py`.
- `quant.services.full_experiment` includes a Backtest DAG step but stays
  safe by default through dry-run behavior and no-live-trading enforcement.

No live broker, account, order-placement, or execution code should be added for
the cloud MVP.

### Configuration and Environment Handling

- Django settings are centralized in `public_monitor/settings.py`.
- Runtime mode and provider-neutral settings live in `src.config.settings`.
- Remote mobile testing settings are built by `public_monitor.remote_mobile`.
- Feature flags resolve through settings, environment variables, SQLite, then
  defaults in `sourceflow.config.feature_flags`.
- `.env.example` documents local defaults plus optional cloud profile values.
- Database config keeps SQLite local by default and can render optional Postgres
  Django settings from `DATABASE_URL` or split `POSTGRES_*` variables.
- The Quant MVP compatibility schema is additive and lives in
  `src.database.core_schema` with Alembic migrations under `alembic/`.
- Compatibility JSON columns use Postgres JSONB and SQLite text JSON through a
  SQLAlchemy type decorator.
- The DuckDB analytical layer lives in `src.warehouse` and reads local or
  object-store-mirrored Parquet partitions without pandas materialization.
- The feature pipeline lives in `src.features`, generates long-form versioned
  features from DuckDB views, and can persist aggregated metadata into the
  compatibility `features` table.
- The object storage facade lives in `src.storage` and writes data lake objects,
  model artifacts, reports, logs, cached datasets, and `_manifest.json` files
  through local or S3-compatible providers.
- The forecast model layer lives in `src.models` with CPU baselines,
  local-checkpoint pretrained adapters, optional PyTorch sequence architectures,
  and Parquet/signals persistence helpers.
- Provider facades live under `src.providers` for storage, database, warehouse,
  queue, secrets, compute, and model registry. Optional SDK imports stay inside
  provider implementations.
- `src.providers.provenance.build_provider_provenance()` records non-secret
  provider choices for Quant experiment provenance.
- The API facade lives in `src.api` and exposes provider-neutral FastAPI routes
  over health, runtime config, jobs, compatibility reads, model registry, and
  storage presigning.

Future cloud settings should be provider-neutral and support local defaults.

### Docker, CI, Scripts, and Tests

- `Dockerfile`, `docker-compose.local.yml`, and `docker-compose.cloud-mvp.yml`
  provide local and one-VPS cloud MVP deployment scaffolding.
- `docker-compose.postgres.yml` remains optional local Postgres test
  scaffolding.
- Test entrypoints are Django tests through `manage.py test` and Playwright e2e
  scripts through `package.json`.
- Python dependencies are declared in `pyproject.toml` and `requirements.txt`.
- Optional NLP dependencies are in `monitoring/nlp/requirements.txt`.
- Optional Postgres compatibility testing uses `POSTGRES_TEST_DATABASE_URL`.
- DuckDB warehouse usage is documented in `docs/duckdb_warehouse.md` and can be
  invoked with `python -m src.cli warehouse build-panel`.
- Feature pipeline usage is documented in `docs/feature_pipeline.md` and can be
  invoked with `python -m src.cli features build`.
- CLI usage is documented in `docs/cli.md`.
- Object storage facade usage is documented in `docs/object_storage.md`.
- Cheapest cloud MVP deployment is documented in `docs/deployment_mvp.md`.
- Pre-trained model layer usage is documented in `docs/model_layer.md`.
- API facade usage is documented in `docs/api_facade.md`.
- The reliable verification environment for this Windows checkout is
  `.\.venv-win\Scripts\python.exe`.

Cloud deployment files are budget-first MVP scaffolding; local development does
not depend on containers.
Budget-first architecture rules are codified in
`docs/architecture/budget_first_rules.md` and enforced by dependency-light tests.

## Gaps To Fill For Cloud MVP

- Optional real MinIO or S3-compatible smoke coverage.
- Optional VPS hardening: reverse proxy TLS, backups, and managed Postgres/R2
  overrides.
- Optional real pretrained dependencies and checkpoints for Chronos, PatchTST,
  NeuralProphet, TimesFM, Fin-Mamba, and production SAMBA weights.

## Preservation Rules

- Keep SQLite as the default and keep current migrations compatible.
- Do not delete or bypass existing Quant, QuantSpace, Sourceflow, or
  monitoring modules.
- Do not hardcode cloud vendor SDKs into business logic.
- Do not introduce expensive or heavy dependencies as required dependencies.
- Do not add Kubernetes, Kafka, Spark, managed vector DB, always-on GPU, or an
  expensive observability stack as required MVP infrastructure.
- Every cloud component must have a local fallback.
- Preserve no-paid-API, no-live-trading, and no-fake-metrics boundaries.
