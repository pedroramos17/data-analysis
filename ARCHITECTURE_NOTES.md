# Hybrid Quant MVP Architecture Notes

Status: Phase 0 audit

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
  Quant4, and QuantSpace.
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
- `quant4.models` owns shared Quant4 metadata:
  `Asset`, `MarketDataset`, `Experiment`, `WindowArtifact`,
  `FeatureArtifact`, `RegimeRun`, `RiskRun`, `LOBRun`, `GraphSnapshot`,
  `PortfolioRun`, `ModelRun`, `BacktestRun`, and `ExplainabilityReport`.
- `quantspace.models` owns local paper, chunk, artifact, question, citation,
  extraction, and factor-candidate metadata.

The cloud MVP should keep these schemas compatible. New cloud/provider metadata
should be additive and migration-safe.

### Parquet and Data Lake Usage

Existing analytical storage is local-path based:

- `monitoring.exporters.ArrowTableWriter` writes document exports to Parquet.
- `sourceflow.finance_ingestion.parquet_export` writes finance rows through a
  thin PyArrow boundary.
- `quantspace.services.chunk_export` writes local paper chunks to Parquet.
- `quant4.services.multifractal.data.parquet_store` writes partitioned OHLCV
  bars and return datasets.
- `quant4.services.multifractal.features.feature_store` writes feature matrices
  to Parquet.
- Local artifact roots include `exports/`, `media/`, `data/`, and
  command-specific output directories.

No DuckDB dependency or DuckDB query facade is currently present. DuckDB should
be added later as an optional embedded OLAP engine over existing Parquet roots.

### Ingestion Modules

Current ingestion is command-driven and local-first:

- Monitoring ingestion handles RSS/HTML/API records through
  `monitoring.ingestion`, `monitoring.ingestion_v2`, fetchers, parsers,
  normalizers, and storage helpers.
- Sourceflow finance ingestion includes local files, SEC EDGAR, FRED, CFTC
  COT, Yahoo research, public web policy gates, normalization, quality checks,
  and global market windows.
- Quant4 ingestion commands include asset registration, price ingestion, LOB
  ingestion, multifractal CSV bar import, return generation, and full
  experiment orchestration.
- QuantSpace ingestion handles local PDF upload and paper chunking.

Cloud ingestion should wrap storage, secrets, and queues behind providers. It
must not place cloud SDK calls in these business modules.

### Feature Engineering and Research Modules

Quant4 already contains local CPU-first research modules:

- Core data foundation, calendars, corporate actions, futures rolls, FX
  normalization, windows, labels, leakage checks, feature store, factor store,
  evaluation, and reports.
- MarketLab under `quant4/services/marketlab/` for windowing, shuffling, TDA,
  signatures, decomposition, graphs, contrastive workflows, benchmarks, and
  experimental backtests.
- Graph and topology lab under `quant4/services/graphs/`.
- Risk and regime services under `quant4/services/risk/`.
- Portfolio services under `quant4/services/portfolio/`.
- LOB and microstructure services under `quant4/services/lob/`.
- Multifractal services under `quant4/services/multifractal/`.

These modules should remain local-first. Cloud execution should provide
artifact locations and job handles, not duplicate research code.

### Model Training and Inference

Current model support is intentionally light:

- `quant4.services.registry` registers components by category and feature flag.
- `quant4.services.full_experiment` plans a safe DAG with optional dependency
  skips for Torch, Torch Geometric, CVXPY, signature, RQA, and graph extras.
- `quant4.services.lob.deeplob` contains local baselines and optional
  PyTorch-gated DeepLOB/TCN-LOB stubs.
- `quant4.services.multifractal.ml.baselines` uses a deterministic majority
  fallback and optional scikit-learn baselines.
- `sourceflow.finance_models.mci_gru_gnn_spec` documents feature-flagged
  MCI-GRU/GNN architecture specs.

SAMBA, Mamba, and Fin-Mamba should enter as optional model registry hooks with
pre-trained artifact references. MVP inference should be CPU-first. GPU batch
jobs should be provider-backed and optional, never a paid managed GPU
requirement.

### Backtest and Portfolio Surfaces

- Quant4 portfolio optimization stores `PortfolioRun` metadata and artifact
  paths for weights, trades, metrics, and risk reports.
- MarketLab has experimental backtest services under
  `quant4/services/marketlab/backtest.py`.
- `quant4.services.full_experiment` includes a Backtest DAG step but stays
  safe by default through dry-run behavior and no-live-trading enforcement.

No live broker, account, order-placement, or execution code should be added for
the cloud MVP.

### Configuration and Environment Handling

- Django settings are centralized in `public_monitor/settings.py`.
- Remote mobile testing settings are built by `public_monitor.remote_mobile`.
- Feature flags resolve through settings, environment variables, SQLite, then
  defaults in `sourceflow.config.feature_flags`.
- `.env.example` exists but there is no Pydantic settings layer yet.
- There is no `DATABASE_URL` parser, Postgres profile, cloud provider config,
  object storage config, queue config, or secrets provider config yet.

Future cloud settings should be provider-neutral and support local defaults.

### Docker, CI, Scripts, and Tests

- No Dockerfile, compose file, or GitHub Actions workflow is currently present.
- Test entrypoints are Django tests through `manage.py test` and Playwright e2e
  scripts through `package.json`.
- Python dependencies are declared in `pyproject.toml` and `requirements.txt`.
- Optional NLP dependencies are in `monitoring/nlp/requirements.txt`.
- The reliable verification environment for this Windows checkout is
  `.\.venv-win\Scripts\python.exe`.

Cloud deployment files should be added as budget-first MVP scaffolding later,
without making local development depend on containers.

## Gaps To Fill For Cloud MVP

- Provider-neutral settings object for environment mode, budget limits, and
  local/cloud resource endpoints.
- Database provider abstraction that keeps SQLite local and adds Postgres as an
  optional cloud transactional profile.
- Object storage facade with local filesystem default and optional
  S3-compatible adapters for MinIO, Cloudflare R2, Backblaze B2, or AWS S3.
- DuckDB analytical facade over existing Parquet roots.
- Compute provider facade for local sync execution, local queued execution,
  and future batch GPU job manifests.
- Secrets provider facade with environment/local file defaults and future cloud
  provider adapters.
- Queue provider facade with a local in-process/null queue default.
- Model registry facade that can register local artifact paths and future
  object-storage URIs.
- Optional pre-trained SAMBA/Mamba/Fin-Mamba hooks behind feature flags.

## Preservation Rules

- Keep SQLite as the default and keep current migrations compatible.
- Do not delete or bypass existing Quant4, QuantSpace, Sourceflow, or
  monitoring modules.
- Do not hardcode cloud vendor SDKs into business logic.
- Do not introduce expensive or heavy dependencies as required dependencies.
- Every cloud component must have a local fallback.
- Preserve no-paid-API, no-live-trading, and no-fake-metrics boundaries.
