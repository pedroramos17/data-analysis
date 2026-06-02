# Hybrid Quant MVP TODO

Status: active Phase 0 checklist

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
- [ ] Add local fallback interfaces for database, storage, analytics, compute,
  queue, secrets, and model registry.
- [x] Add tests that every provider category resolves locally without optional
  cloud dependencies.
- [x] Document environment variables and local fallback behavior.

## Phase 2: Database Profiles

- [ ] Keep SQLite as the default Django database profile.
- [ ] Add optional Postgres profile rendering from environment variables or
  `DATABASE_URL`.
- [ ] Add clear missing-driver errors for selected Postgres mode.
- [ ] Add tests for SQLite default and optional Postgres config.

## Phase 3: DuckDB Analytics Over Parquet

- [ ] Add optional DuckDB analytics provider over existing Parquet artifacts.
- [ ] Preserve existing PyArrow write/read paths.
- [ ] Add fallback behavior when DuckDB is missing.
- [ ] Add tests with local Parquet fixtures.

## Phase 4: Object Storage Facade

- [ ] Add local filesystem storage provider.
- [ ] Add optional S3-compatible provider interface for MinIO, Cloudflare R2,
  Backblaze B2, and AWS S3.
- [ ] Keep bucket, endpoint, key, and region values in settings/secrets.
- [ ] Add fake-provider and local-provider tests.

## Phase 5: Compute, Queue, Secrets, And Model Registry

- [ ] Add local synchronous compute provider.
- [ ] Add no-op or in-memory local queue provider.
- [ ] Add environment-backed local secrets provider.
- [ ] Add local model registry provider for pre-trained artifact references.
- [ ] Record provider metadata in Quant4 run provenance.

## Phase 6: Pre-trained Time-Series Model Hooks

- [ ] Add SAMBA model spec hook behind a feature flag.
- [ ] Add Mamba model spec hook behind a feature flag.
- [ ] Add Fin-Mamba model spec hook behind a feature flag.
- [ ] Keep CPU-first inference as the MVP default.
- [ ] Represent optional GPU work as batch job manifests only.
- [ ] Add tests for missing optional dependencies and no performance claims.

## Phase 7: Budget-First Cloud Deployment

- [ ] Add cheap cloud MVP deployment notes after provider facades exist.
- [ ] Keep local development container-optional.
- [ ] Add optional MinIO smoke path for local object-storage testing.
- [ ] Add budget guard settings and dry-run examples.
- [ ] Add validation commands for local and cheap-cloud profiles.

## Always-On Constraints

- [ ] Do not delete SQLite mode.
- [ ] Do not break existing migrations.
- [ ] Do not hardcode cloud SDKs into business logic.
- [ ] Do not add required paid APIs or managed GPU dependencies.
- [ ] Keep every cloud component backed by a local fallback.
- [ ] Keep no-live-trading and no-fake-metrics boundaries explicit.
