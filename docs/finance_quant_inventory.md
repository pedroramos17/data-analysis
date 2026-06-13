# Finance And Quant Inventory

Status: Phase 0 complete, retroactive inventory

Date: 2026-06-13

This inventory was completed after the package rename to `quant` and after the
ResearchSpace rename. Legacy names are intentionally not preserved.

## Scope

This inventory covers current finance and quant code and docs in these areas:

- `quant/`
- `sourceflow/finance_core/`
- `sourceflow/warehouse/`
- `sourceflow/finance_ingestion/`
- `sourceflow/finance_dataset/`
- `sourceflow/finance_features/`
- `sourceflow/finance_graph/`
- `sourceflow/finance_models/`
- `sourceflow/finance_stats/`
- finance, market, dataset, and factor commands under `monitoring/management/commands/`
- active finance, quant, MarketLab, market data, and ResearchSpace docs under `docs/`

Rows below are evaluated from most specific to least specific. If a file matches
a more specific row, that row is the classification. If it only matches a broad
directory row, the broad row is the classification. This covers every current
finance and quant file in the scope above.

## Actions

| Action | Meaning |
| --- | --- |
| `KEEP_AS_IS` | Boundary is already correct for the current phase. |
| `KEEP_AND_MOVE` | Keep behavior, but move it to the target boundary. |
| `KEEP_AS_COMPAT_WRAPPER` | Temporary wrapper only when persisted external callers require it. Current decision: avoid unless tests prove a need. |
| `MERGE_INTO_WAREHOUSE` | Move or wrap storage, manifest, registry, Parquet, Arrow, or filesystem behavior in `sourceflow.warehouse`. |
| `MERGE_INTO_FINANCE_CORE` | Move shared records, schemas, enums, time helpers, or identifiers into `sourceflow.finance_core`. |
| `MOVE_TO_QUANT` | Move research, model, risk, portfolio, regime, backtest, LOB, graph-lab, or optional research-engine behavior under `quant`. |
| `DELETE_AFTER_TESTS` | Delete after replacement docs/tests are present and Django checks can run. |

## Code Classification

| Path | Classification | Target / Notes |
| --- | --- | --- |
| `sourceflow/finance_core/*.py` | `KEEP_AS_IS` | New shared contract boundary. Add tests next. |
| `sourceflow/warehouse/__init__.py` | `KEEP_AS_IS` | New storage boundary package. |
| `sourceflow/warehouse/paths.py` | `KEEP_AS_IS` | Warehouse-owned path helper. |
| `sourceflow/warehouse/atomic_write.py` | `KEEP_AS_IS` | Warehouse-owned local atomic-write helper. |
| `sourceflow/warehouse/manifests.py` | `KEEP_AS_IS` | Warehouse-owned manifest builder. Expand for all manifests. |
| `sourceflow/warehouse/parquet_io.py` | `KEEP_AS_IS` | Warehouse-owned Parquet writer. Add read/partition support. |
| `sourceflow/finance_ingestion/parquet_export.py` | `MERGE_INTO_WAREHOUSE` | Current wrapper delegates to `sourceflow.warehouse.parquet_io`; delete or keep as thin caller only after commands/tests are updated. |
| `sourceflow/finance_dataset/manifests.py` | `MERGE_INTO_WAREHOUSE` | Current wrapper delegates to `sourceflow.warehouse.manifests`; delete or keep as dataset API facade after tests. |
| `sourceflow/finance_ingestion/connectors/*.py` | `KEEP_AND_MOVE` | Move or wrap under `sourceflow.finance_ingestion.providers`. Providers must emit `RawSnapshot` and canonical records only. |
| `sourceflow/finance_ingestion/quality.py` | `KEEP_AND_MOVE` | Move quality gates into raw/bronze/silver/gold pipeline services or warehouse quality reports depending on usage. |
| `sourceflow/finance_ingestion/normalization.py` | `MERGE_INTO_FINANCE_CORE` | Shared canonical row normalization belongs beside `BarRecord` and row converters when provider-neutral. |
| `sourceflow/finance_ingestion/policies.py` | `KEEP_AS_IS` | Ingestion policy boundary is acceptable if it has no training/backtest behavior. |
| `sourceflow/finance_ingestion/global_market_windows.py` | `KEEP_AND_MOVE` | Window materialization belongs in ingestion pipeline or finance dataset depending on whether labels/splits are involved. |
| `sourceflow/finance_dataset/build_dataset.py` | `KEEP_AS_IS` | Keep in dataset boundary, but ensure it reads only warehouse-managed data. |
| `sourceflow/finance_dataset/leakage.py` | `KEEP_AS_IS` | Dataset-owned anti-leakage behavior. |
| `sourceflow/finance_dataset/splits.py` | `KEEP_AS_IS` | Dataset-owned split behavior. |
| `sourceflow/finance_dataset/targets.py` | `KEEP_AS_IS` | Dataset-owned target/label definitions. |
| `sourceflow/finance_features/multifractal/*.py` | `KEEP_AS_IS` | Already under deterministic feature boundary. Add registry metadata and equality tests. |
| `sourceflow/finance_features/__init__.py` | `KEEP_AS_IS` | Add registry exports later. |
| `sourceflow/finance_graph/*.py` | `KEEP_AND_MOVE` | Split source-comparison graph behavior from finance feature graph behavior. Finance-only graph feature builders belong under `finance_features` or `quant` graph research. |
| `sourceflow/finance_models/*.py` | `MOVE_TO_QUANT` | Forecasting, training, model evaluation, and XAI model behavior should become optional quant engines or quant model adapters. Pure contracts can move to `finance_core`. |
| `sourceflow/finance_stats/*.py` | `KEEP_AS_IS` | Deterministic statistics can remain as shared finance analytics. Promote feature-producing stats through `finance_features.registry`. |
| `sourceflow/intelligence/market/contracts.py` | `MERGE_INTO_FINANCE_CORE` | Completed: finance-like market records moved into `sourceflow.finance_core.contracts`; mixed contract file removed. |
| `sourceflow/intelligence/market/*.py` | `KEEP_AND_MOVE` | Separate market data/feature code from source/document/event comparison code. Finance-only logic moves to finance boundaries. |
| `quant/apps.py`, `quant/admin.py`, `quant/models.py`, `quant/migrations/*.py` | `KEEP_AS_IS` | Django app metadata and local research registry. Migrations represent fresh local schema. |
| `quant/management/commands/quant_*.py` | `KEEP_AS_IS` | Renamed quant commands. Later align with stable command chain and warehouse/finance-core contracts. |
| `quant/management/commands/marketlab_*.py` | `KEEP_AS_IS` | MarketLab research commands stay in `quant`; ensure no provider API calls. |
| `quant/services/assets.py`, `quant/services/calendars.py`, `quant/services/corporate_actions.py` | `MERGE_INTO_FINANCE_CORE` | Shared market metadata and calendar contracts should be provider-neutral shared finance utilities unless tied to research runs. |
| `quant/services/data_ingestion.py`, `quant/services/data_quality.py` | `KEEP_AND_MOVE` | Ingestion/quality behavior should move to `finance_ingestion` or `warehouse`; quant should consume outputs. |
| `quant/services/feature_store.py`, `quant/services/factor_store.py` | `KEEP_AND_MOVE` | Deterministic feature/factor storage belongs in `finance_features` or `warehouse`; research-only factor experiments can stay under quant. |
| `quant/services/full_experiment.py` | `KEEP_AS_IS` | Quant orchestration; update to consume `GoldDataset`, `FeatureFrame`, `LabelFrame`, and warehouse artifact pointers. |
| `quant/services/graphs/*.py` | `MOVE_TO_QUANT` | Research graph builders/filters stay in quant, later under `quant/graph` or `quant/backtesting` as appropriate. |
| `quant/services/labels.py`, `quant/services/leakage.py`, `quant/services/windows.py` | `KEEP_AND_MOVE` | Generic dataset labels, leakage, and windows move to `finance_dataset`; quant-specific experiment wrappers can remain. |
| `quant/services/lob/*.py` | `KEEP_AS_IS` | LOB research boundary. Ensure data access goes through warehouse artifacts. |
| `quant/services/marketlab/*.py` | `KEEP_AS_IS` | MarketLab remains quant research. Keep optional engines/adapters explicit. |
| `quant/services/multifractal/core/*.py` | `KEEP_AS_IS` | Research algorithms stay in quant unless deterministic feature extraction is isolated. |
| `quant/services/multifractal/data/contracts.py` | `MERGE_INTO_FINANCE_CORE` | Completed for bars: `OHLCVBar` now points at `sourceflow.finance_core.BarRecord`; quant-specific return/write-result records remain here. |
| `quant/services/multifractal/data/parquet_store.py` | `MERGE_INTO_WAREHOUSE` | Partitioned Parquet read/write belongs in warehouse. |
| `quant/services/multifractal/data/sqlite_registry.py` | `MERGE_INTO_WAREHOUSE` | Local artifact registry belongs in warehouse. |
| `quant/services/multifractal/data/validators.py` | `KEEP_AND_MOVE` | Bar/return validation belongs with `finance_core` contracts or dataset builders; method-specific validation can stay in quant. |
| `quant/services/multifractal/features/*.py` | `KEEP_AND_MOVE` | Deterministic features move to `sourceflow.finance_features.multifractal`; research-only wrappers can stay. |
| `quant/services/multifractal/lob/*.py` | `KEEP_AS_IS` | LOB-specific multifractal research stays in quant. |
| `quant/services/multifractal/ml/*.py` | `KEEP_AS_IS` | Research modeling stays in quant. Later move under `quant/engines` if generalized. |
| `quant/services/multifractal/models/*.py` | `KEEP_AS_IS` | Research model implementations stay in quant. |
| `quant/services/multifractal/plots/*.py` | `KEEP_AS_IS` | Research reporting artifact helpers stay in quant. |
| `quant/services/multifractal/portfolio/*.py` | `KEEP_AS_IS` | Quant research portfolio behavior. Later align return types with `BacktestResult` or portfolio run contracts. |
| `quant/services/multifractal/preprocessing/*.py` | `KEEP_AND_MOVE` | Generic leakage-safe windows/returns/scaling can move to `finance_dataset` or `finance_features`; method-specific preprocessing can remain. |
| `quant/services/multifractal/regime/*.py` | `KEEP_AS_IS` | Quant regime research boundary. |
| `quant/services/multifractal/reports/*.py` | `KEEP_AS_IS` | Quant reporting boundary. |
| `quant/services/multifractal/risk/*.py` | `KEEP_AS_IS` | Quant risk research boundary. |
| `quant/services/multifractal/synthetic.py` | `KEEP_AS_IS` | Research fixtures/generators stay in quant unless reused by finance-core tests. |
| `quant/services/portfolio/*.py` | `KEEP_AS_IS` | Quant portfolio research and optional package adapters stay in quant. |
| `quant/services/regimes/*.py` | `KEEP_AS_IS` | Quant regime research stays in quant. |
| `quant/services/registry.py` | `KEEP_AS_IS` | Optional component registry stays in quant until a cross-boundary plugin registry is needed. |
| `quant/services/reports.py` | `KEEP_AS_IS` | Quant reporting helpers stay in quant. |
| `quant/services/risk/*.py` | `KEEP_AS_IS` | Quant risk research stays in quant. |
| `quant/services/run_metadata.py` | `MERGE_INTO_FINANCE_CORE` | Date range and reproducibility helpers should be shared contracts if used outside quant. |
| `quant/tests/*.py` | `KEEP_AS_IS` | Tests stay under `quant/tests/` per separated module policy. Add new sourceflow tests separately. |
| `monitoring/management/commands/ingest_market_data.py` | `KEEP_AND_MOVE` | Update to target `--provider`; call `finance_ingestion.providers` and pipeline services instead of direct monitoring model writes. |
| `monitoring/management/commands/import_market_snapshot.py` | `KEEP_AND_MOVE` | Move parsing/materialization into ingestion pipeline; command remains a thin Django entrypoint. |
| `monitoring/management/commands/build_global_market_windows.py` | `KEEP_AND_MOVE` | Move window logic to ingestion pipeline or dataset boundary. |
| `monitoring/management/commands/export_finance_parquet.py` | `MERGE_INTO_WAREHOUSE` | Command should call warehouse APIs directly after wrappers are retired. |
| `monitoring/management/commands/build_prediction_dataset.py` | `KEEP_AND_MOVE` | Replace with target `build_finance_dataset` command using warehouse-backed data. |
| `monitoring/management/commands/import_financial_dataset.py` | `KEEP_AND_MOVE` | Move import/materialization into warehouse or dataset builder; command remains thin. |
| `monitoring/management/commands/compute_multifractal_features.py` | `KEEP_AND_MOVE` | Replace with target `build_finance_features --set multifractal_v1`. |
| `monitoring/management/commands/train_finance_baseline.py` | `MOVE_TO_QUANT` | Replace with target `quant_run_baseline`; training belongs in quant. |
| `monitoring/management/commands/explain_finance_prediction.py` | `MOVE_TO_QUANT` | Model explanation belongs in quant unless explaining monitoring alerts. |
| `monitoring/management/commands/*factor*.py` | `KEEP_AND_MOVE` | Sourceflow symbolic factor commands need split: source intelligence stays in monitoring/sourceflow; finance feature/factor computation moves to finance_features or quant. |

## Command Coverage Snapshot

| Command group | Current files | Covered by current tests | Next action |
| --- | --- | --- | --- |
| Quant registry/data prep | `quant_register_assets`, `quant_ingest_prices`, `quant_import_bars`, `quant_compute_returns`, `quant_prepare_windows` | `quant/tests/test_core.py`, `quant/tests/test_multifractal_data.py`, `quant/tests/test_multifractal_cli.py` | Move generic data prep behind finance ingestion, dataset, and warehouse APIs. |
| Quant risk/regime/portfolio | `quant_run_risk`, `quant_detect_regimes`, `quant_optimize_portfolio` | `quant/tests/test_risk_regime.py`, `quant/tests/test_portfolio.py` | Keep under quant; align inputs with warehouse artifacts. |
| Quant graph/LOB | `quant_build_graphs`, `quant_ingest_lob`, `quant_train_lob_model` | `quant/tests/test_graph_lab.py`, `quant/tests/test_lob_lab.py` | Keep under quant; remove direct provider assumptions. |
| Quant full experiment | `quant_run_full_experiment` | `quant/tests/test_full_experiment.py` | Keep orchestrator; consume `GoldDataset` and `FeatureFrame`. |
| Quant multifractal CLI | `quant_mfdfa`, `quant_mf_diagnostics`, `quant_mf_features`, `quant_mf_regime`, `quant_mf_risk`, `quant_mf_portfolio`, `quant_mf_report` | `quant/tests/test_multifractal_cli.py` plus focused multifractal tests | Move deterministic features/storage to finance boundaries; keep research methods in quant. |
| MarketLab | `marketlab_prepare_windows`, `marketlab_detect_regimes`, `marketlab_run_benchmark`, `marketlab_validate_shuffles` | `quant/tests/test_marketlab.py` and cookbook tests | Keep as quant research commands. |
| Current finance ingestion | `ingest_market_data`, `import_market_snapshot`, `build_global_market_windows` | Existing monitoring tests not fully mapped in this pass | Replace internals with providers and pipeline services. |
| Current finance dataset/export | `build_prediction_dataset`, `import_financial_dataset`, `export_finance_parquet` | Existing monitoring tests not fully mapped in this pass | Replace with `build_finance_dataset` and warehouse APIs. |
| Current finance modeling | `train_finance_baseline`, `explain_finance_prediction` | Existing monitoring tests not fully mapped in this pass | Replace with quant-owned baseline/explanation commands. |
| Current finance features/factors | `compute_multifractal_features`, `compute_factors`, `compute_symbolic_factors`, factor registry/search/evaluation commands | Symbolic factor tests under `monitoring/tests/` | Split source-intelligence symbolic factors from finance feature registry. |

## Missing Target Commands

These target commands from the refactor plan do not exist yet:

- `build_market_layer`
- `build_finance_features`
- `build_finance_dataset`
- `quant_run_baseline`

`ingest_market_data` exists, but it currently uses `--source` rather than the
target `--provider` contract and writes monitoring models directly.

## Test Coverage Snapshot

| Boundary | Current tests | Gap |
| --- | --- | --- |
| `quant` | `quant/tests/*.py` | Cannot run until Django dependency is installed. |
| `researchspace` | `researchspace/tests/*.py` | Cannot run until Django dependency is installed. |
| `sourceflow.finance_core` | `sourceflow/finance_core/tests/test_contracts.py` | Add broader schema and enum tests as the boundary grows. |
| `sourceflow.warehouse` | none | Add tests for manifest determinism, partition paths, atomic writes, and Parquet round-trip with optional pyarrow gating. |
| `sourceflow.finance_ingestion` | no dedicated package tests found | Add provider and pipeline tests. |
| `sourceflow.finance_dataset` | no dedicated package tests found | Add leakage, split, target, and dataset manifest tests. |
| `sourceflow.finance_features` | no dedicated package tests found | Add deterministic feature registry and TIN equality tests. |
| `monitoring` integration | existing `monitoring/tests/` | Keep only tests for Django UI and monitoring integration surfaces. |

## Documentation Inventory

| Path | Classification | Notes |
| --- | --- | --- |
| `docs/finance_quant_refactor_phases.md` | `KEEP_AS_IS` | Active implementation plan. |
| `docs/finance_quant_inventory.md` | `KEEP_AS_IS` | Phase 0 inventory. |
| `docs/financial_data_ingestion.md` | `KEEP_AND_MOVE` | Update after provider/pipeline boundary lands. |
| `docs/finance_graph_model.md` | `KEEP_AND_MOVE` | Split source-intelligence graph vs finance/quant graph docs. |
| `docs/market_intelligence.md` | `KEEP_AND_MOVE` | Update after market contracts move to finance_core. |
| `docs/multifractal_features.md` | `KEEP_AND_MOVE` | Align with finance feature registry. |
| `docs/marketlab.md` | `KEEP_AS_IS` | Current MarketLab doc; keep under quant research story. |
| `docs/marketlab_leakage.md` | `KEEP_AS_IS` | Current MarketLab safety doc. |
| `docs/marketlab_shuffling_tda.md` | `KEEP_AS_IS` | Current MarketLab methods doc. |
| `docs/next_gen_finance_roadmap.md` | `KEEP_AND_MOVE` | Fold active content into phase plan or current architecture docs. |
| `docs/researchspace*.md` | `KEEP_AS_IS` | Current ResearchSpace docs. |
| `docs/compliance_market_data.md` | `KEEP_AS_IS` | Current safety/compliance doc. |
| `docs/compute_profiles.md`, `docs/local_low_end_setup.md`, `docs/cloud_student_setup.md`, `docs/control_dashboard.md`, `docs/mobile_data_testing.md`, `docs/feature_flags.md` | `KEEP_AS_IS` | Operational docs, not stale finance architecture. |
| deleted legacy quant docs in current worktree | `DELETE_AFTER_TESTS` | Stale after rename and replacement phase plan. |
| deleted legacy ResearchSpace-name docs in current worktree | `DELETE_AFTER_TESTS` | Replaced by `docs/researchspace*.md`. |
| deleted `docs/multifractal/*.md` phase notes | `DELETE_AFTER_TESTS` | Superseded by active phase plan and current feature docs. |
| deleted `ARCHITECTURE_NOTES.md`, `MIGRATION_PLAN.md`, `HANDOFF.md` | `DELETE_AFTER_TESTS` | Superseded by active plan and inventory. |

## Stale Docs Decision

The current active docs contain no legacy quant or ResearchSpace names after the
rename grep. Deleted docs are intentionally classified as `DELETE_AFTER_TESTS`
installed.

## Phase 0 Acceptance Status

| Acceptance item | Status |
| --- | --- |
| Classification exists for every finance and quant file. | Complete by scoped path-pattern rules above. |
| Active docs state legacy local SQLite data is disposable. | Complete in `docs/finance_quant_refactor_phases.md`. |
| No code movement happens before inventory is complete. | Waived retroactively: rename and initial scaffolding already happened before this inventory. Further moves should follow this document. |

## Validation Notes

The dependency-free validation from the rename pass was:

- stale-name grep clean for Python, Markdown, templates, and ignored paths
- `git diff --check` passed
- changed Python files compiled with `python3 -m py_compile`
- `python3 -m unittest sourceflow.finance_core.tests.test_contracts` passed

Django checks and Django tests are blocked in this environment until the `django`
package is installed.
