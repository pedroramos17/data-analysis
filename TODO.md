# Finance And Quant Refactor TODO

Status: active checklist

See `docs/finance_quant_refactor_phases.md` for the full phased plan.

## Phase 0: Inventory And Freeze Points

- [x] Document the phased finance/quant boundary refactor.
- [x] Record that the legacy quant app name becomes `quant` everywhere.
- [x] Record that existing local SQLite data from the legacy quant app is not preserved.
- [x] Classify every current finance and quant file.
- [x] Record current command coverage and tests before the rename.
- [x] Identify any remaining stale docs before moving code.

## Phase 1: Rename Legacy Quant App To Quant

- [x] Rename package to `quant/`.
- [x] Rename Django app config to `QuantConfig` and update `INSTALLED_APPS`.
- [x] Rename imports to `quant.*`.
- [x] Rename management commands to `quant_*`.
- [x] Rename feature flags to `QUANT_*`.
- [x] Rewrite migrations for a fresh `quant` local schema.
- [x] Delete compatibility namespaces and aliases.

## Phase 2: Finance Core Contracts

- [x] Add `sourceflow.finance_core`.
- [x] Define shared finance records, datasets, frames, signals, and backtest results.
- [x] Move finance-like market contracts out of mixed sourceflow intelligence modules.

## Phase 3: Warehouse Foundation

- [x] Add `sourceflow.warehouse`.
- [ ] Consolidate manifests, Parquet, Arrow, optional Feather, DuckDB, SQLite, and optional Postgres helpers.
- [ ] Move partitioned Parquet and registry logic behind warehouse APIs.

## Phase 4: Provider-Neutral Ingestion

- [ ] Add provider adapters under `sourceflow.finance_ingestion.providers`.
- [ ] Add raw, bronze, silver, and gold pipeline builders.
- [ ] Update management commands to call pipeline services.

## Phase 5: Dataset Boundary Cleanup

- [ ] Keep dataset code limited to leakage checks, splits, targets, labels, and dataset manifests.
- [ ] Remove provider imports and technical indicators from dataset code.

## Phase 6: Deterministic Feature Registry

- [ ] Add deterministic feature registry.
- [ ] Add technical indicators.
- [ ] Move multifractal deterministic features under `sourceflow.finance_features`.
- [ ] Add TIN fixed-output layers and equality tests.

## Phase 7: Quant Research Boundary

- [ ] Keep research engines, adapters, backtests, risk, portfolio, regimes, and RL under `quant`.
- [ ] Ensure external packages are adapters or optional engines only.
- [ ] Ensure quant research consumes warehouse artifacts and finance contracts, not provider APIs.

## Phase 8: Stable Command Chain

- [ ] Implement `ingest_market_data --provider ...`.
- [ ] Implement `build_market_layer` for bronze and silver.
- [ ] Implement `build_finance_features` sets.
- [ ] Implement `build_finance_dataset`.
- [ ] Implement `quant_run_baseline`.

## Phase 9: Documentation And Dead-Code Cleanup

- [ ] Delete stale docs after current replacements exist.
- [ ] Delete compatibility wrappers after imports are updated and tests pass.
- [ ] Verify no active code or docs reintroduce legacy quant naming except in migration notes.
