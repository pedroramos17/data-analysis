# Hybrid Quant MVP Migration Plan

Status: Phase 0 plan

Date: 2026-06-02

## Goal

Move the existing offline-first quant research platform toward a cheap
cloud-ready MVP while preserving local SQLite mode and the current Django,
Quant4, QuantSpace, Sourceflow, Parquet, and command structure.

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
- Keep provider interfaces under Quant4 or a shared project namespace that
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

- Do not replace Django ORM with SQLAlchemy/Alembic because this repo already
  uses Django migrations.
- Add a configuration helper, not business-logic conditionals.
- Add tests for SQLite default, Postgres config rendering, and missing driver
  error messaging.

## Phase 3: DuckDB Analytics Over Parquet

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

## Phase 4: Object Storage Facade

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

## Phase 5: Compute, Queue, Secrets, And Model Registry Facades

Add cheap-cloud-ready control-plane abstractions while retaining local sync
execution.

Planned behavior:

- Compute provider supports local synchronous execution and future batch job
  manifests.
- Queue provider supports local no-op/in-memory behavior for MVP tests.
- Secrets provider reads environment variables locally and can later wrap cloud
  secret stores.
- Model registry provider records local model artifacts, pre-trained artifact
  URIs, config hashes, feature schemas, and provenance.
- Quant4 full-experiment DAG can include provider metadata in experiment
  provenance without changing safety rules.

Implementation notes:

- Reuse `quant4.services.registry`, `Experiment`, `ModelRun`, `PipelineJob`,
  and compute profile conventions where possible.
- Do not add live trading, account access, or broker execution paths.
- Add tests that compute and queue providers never fake completed metrics.

## Phase 6: Pre-trained Model Hooks

Add architecture hooks for financial time-series models without making GPU
training required.

Planned behavior:

- Register model specs for SAMBA, Mamba, and Fin-Mamba as optional Quant4 model
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

## Phase 7: Budget-First Cloud Deployment

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

## Rollback Strategy

- Keep SQLite profile untouched and default.
- Keep all new cloud settings optional.
- Keep provider integrations behind feature flags or explicit provider
  selection.
- Revert provider modules independently without touching existing research
  commands.
- Validate rollback with `manage.py check`, `manage.py test quant4 quantspace`,
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
