# Finance And Quant Boundary Refactor Phases

Status: active implementation plan

Date: 2026-06-13

## Decisions

- The legacy quant app name is dead. Use `quant` everywhere.
- Existing local SQLite data from the legacy quant app is not preserved.
- Regenerate or rewrite Django migrations for the new `quant` app instead of
  table-renaming old app tables.
- A developer with an old local database must delete or recreate the local
  SQLite database after the rename.
- Do not add legacy-name compatibility imports, command aliases, feature flags, or
  table aliases.
- Keep Django tests separated by module boundary so each area can become a
  future microservice.

## Target Boundaries

```text
sourceflow/
  core source/document/event comparison machine
  no trading/backtesting dependencies

sourceflow/finance_core/
  shared finance contracts, enums, schemas, time helpers, ids
  no provider APIs, model training, backtests, or strategy logic

sourceflow/warehouse/
  filesystem, manifests, parquet, arrow, feather, duckdb, sqlite, postgres I/O
  shared by sourceflow and finance modules

sourceflow/finance_ingestion/
  provider adapters and raw/bronze/silver/gold materialization
  no model training, strategy logic, or research engines

sourceflow/finance_dataset/
  dataset manifests, leakage checks, splits, targets
  no provider APIs or technical indicators

sourceflow/finance_features/
  deterministic feature builders only
  technical indicators, multifractal features, and TIN fixed-output layers

quant/
  Django app and research boundary
  forecasting engines, experiments, backtests, risk, portfolio, regimes, RL adapters
```

## Test Boundaries

Keep tests under the module that owns the behavior:

- `monitoring/tests/`: public-source Django UI, commands, ingestion, dashboard,
  and comparison-machine integration.
- `quant/tests/`: quant Django app models, migrations, management commands,
  run metadata, research orchestration, risk, regime, portfolio, LOB, graph, and
  backtest adapters.
- `sourceflow/finance_core/tests/`: pure contract, schema, identifier, enum, and
  time-normalization tests.
- `sourceflow/warehouse/tests/`: manifest, path, atomic-write, Parquet, Arrow,
  DuckDB, SQLite registry, and optional Postgres adapter tests.
- `sourceflow/finance_ingestion/tests/`: provider adapter and raw/bronze/silver/gold
  pipeline tests.
- `sourceflow/finance_dataset/tests/`: leakage, split, target, label, and dataset
  manifest tests.
- `sourceflow/finance_features/tests/`: technical, multifractal, and TIN
  deterministic feature tests.

Do not place finance-core or quant research tests in `monitoring/tests/` unless
the tested behavior is a monitoring integration surface.

## Phase 0: Inventory And Freeze Points

Goal: classify current files before moving them.

Inventory artifact: `docs/finance_quant_inventory.md`.

Tasks:

- Build a file classification list using:
  `KEEP_AND_MOVE`, `KEEP_AS_COMPAT_WRAPPER`, `MERGE_INTO_WAREHOUSE`,
  `MERGE_INTO_FINANCE_CORE`, `MOVE_TO_QUANT`, and `DELETE_AFTER_TESTS`.
- Record current command coverage and tests for `monitoring`, `sourceflow`, and
  the legacy quant app before the rename.
- Identify docs that are active architecture notes versus stale phase notes.

Acceptance:

- Classification exists for every finance and quant file.
- Active docs state that legacy quant local SQLite data is disposable.
- No further code movement happens without following the inventory.

## Phase 1: Rename Legacy Quant App To Quant

Goal: make the project name match the boundary before deeper refactors.

Tasks:

- Rename package to `quant/`.
- Rename the Django app config to `QuantConfig` and update `INSTALLED_APPS`.
- Rename imports to `quant.*`.
- Rename management commands to `quant_*`.
- Rename feature flags to `QUANT_*`.
- Rename internal strings to `quant_*` and `data/quant_*` names.
- Rewrite migrations for the new `quant` app as a fresh local schema.
- Delete legacy-name compatibility namespaces and command aliases.

Acceptance:

- `python manage.py check` passes.
- `python manage.py makemigrations --check --dry-run` passes after fresh
  migrations are committed.
- `python manage.py test quant` runs the renamed quant test module.
- Searching Python files for legacy quant names returns no active code matches.

## Phase 2: Finance Core Contracts

Goal: define the shapes every finance module must use.

Create:

```text
sourceflow/finance_core/
  __init__.py
  contracts.py
  enums.py
  schemas.py
  time.py
  ids.py
```

Contracts:

- `BarRecord`
- `EventRecord`
- `FundamentalRecord`
- `RawSnapshot`
- `BronzeDataset`
- `SilverPanel`
- `GoldDataset`
- `FeatureFrame`
- `LabelFrame`
- `ForecastFrame`
- `SignalFrame`
- `BacktestResult`

Tasks:

- Merge `quant.services.multifractal.data.contracts.OHLCVBar` into
  `BarRecord` or an explicitly named converter.
- Move finance-like market contracts from `sourceflow.intelligence.market` into
  `finance_core` when they are not source-comparison concepts.
- Add row conversion helpers for Arrow-friendly dictionaries.

Acceptance:

- Provider code, dataset builders, feature builders, and quant services import
  finance shapes from `sourceflow.finance_core`.
- No module invents its own OHLCV dataframe shape.

## Phase 3: Warehouse Foundation

Goal: establish one storage and manifest system.

Create:

```text
sourceflow/warehouse/
  paths.py
  manifests.py
  parquet_io.py
  arrow_io.py
  feather_io.py
  duckdb_views.py
  sqlite_registry.py
  postgres_registry.py
  atomic_write.py
  quality_report.py
```

Tasks:

- Move or wrap `sourceflow.finance_ingestion.parquet_export` into
  `sourceflow.warehouse.parquet_io`.
- Move or wrap `sourceflow.finance_dataset.manifests` into
  `sourceflow.warehouse.manifests`.
- Move partitioned Parquet and registry logic from
  `quant.services.multifractal.data` into `warehouse`.
- Keep Parquet as the durable format and Arrow as the in-memory exchange.
- Keep Feather as optional local scratch/cache only.
- Keep DuckDB as optional Parquet reader.
- Keep SQLite as lightweight local metadata for the current database only; do
  not migrate old legacy quant local SQLite data.

Acceptance:

- There is one manifest system.
- Finance ingestion and dataset code use warehouse I/O instead of local storage
  helpers.
- Warehouse tests cover Parquet round-trips and manifest determinism.

## Phase 4: Provider-Neutral Ingestion

Goal: make provider adapters boring and replaceable.

Create:

```text
sourceflow/finance_ingestion/providers/
  base.py
  csv_provider.py
  yfinance_provider.py
  stooq_provider.py
  fred_provider.py
  openbb_provider.py

sourceflow/finance_ingestion/pipeline/
  raw_writer.py
  bronze_builder.py
  silver_builder.py
  gold_builder.py
```

Tasks:

- Move current connectors under providers or wrap them there.
- Restrict providers to `external response -> RawSnapshot -> canonical records`.
- Move materialization into pipeline builders.
- Update management commands to call pipeline services, not provider internals.

Acceptance:

- Providers do not compute technical indicators.
- Providers do not import quant research modules.
- `ingest_market_data` accepts provider/symbol/timeframe inputs and writes raw
  snapshots without training, strategy, or backtest behavior.

## Phase 5: Dataset Boundary Cleanup

Goal: keep anti-leakage and model-dataset logic separate from ingestion and
features.

Tasks:

- Keep `build_dataset.py`, `leakage.py`, `splits.py`, and `targets.py` in
  `sourceflow.finance_dataset`.
- Remove provider API imports from dataset code.
- Remove technical indicator generation from dataset code.
- Make dataset builders read only warehouse-managed Bronze/Silver/Gold data.

Acceptance:

- `finance_dataset` imports `finance_core` and `warehouse`, not providers.
- Leakage tests live under `sourceflow/finance_dataset/tests/`.

## Phase 6: Deterministic Feature Registry

Goal: make all deterministic features explicit, versioned, and auditable.

Create:

```text
sourceflow/finance_features/registry.py
sourceflow/finance_features/technical/
sourceflow/finance_features/multifractal/
sourceflow/finance_features/tin/
```

Feature builders must declare:

- `name`
- `version`
- `input_schema`
- `output_schema`
- `lookback`
- `uses_future_data = False`
- `parameters_hash`

Tasks:

- Move deterministic multifractal feature code out of `quant` into
  `finance_features`.
- Add technical indicators: MA, RSI, MACD, Bollinger, ADX, OBV, candles.
- Add TIN fixed-output layers: MA, MACD, RSI, stochastic, CCI.

TIN acceptance:

- TIN-MA output equals the SMA/EMA implementation.
- TIN-MACD output equals the classical MACD implementation.
- TIN-RSI output equals the classical RSI implementation.
- TIN layers remain non-trainable until equality tests pass.

## Phase 7: Quant Research Boundary

Goal: keep research engines and external-package adapters away from ingestion,
datasets, and deterministic features.

Target layout:

```text
quant/
  engines/
    statsforecast_engine.py
    darts_engine.py
    neuralforecast_engine.py
  backtesting/
    contracts.py
    adapters/
      vectorbt_adapter.py
      backtrader_adapter.py
  risk/
  portfolio/
  regime/
  rl/
    adapters/
      finrl_env_adapter.py
  execution/
    adapters/
      liualgotrader_adapter.py
```

Tasks:

- Move or wrap existing `quant.services` research modules into the new boundary.
- Keep external packages as adapters or optional engines only.
- Ensure StatsForecast, Darts, NeuralForecast, and FinRL never call raw provider
  APIs directly.

Acceptance:

- Quant research consumes `GoldDataset`, `FeatureFrame`, `LabelFrame`,
  `SignalFrame`, and warehouse artifact pointers.
- Backtests return project-owned `BacktestResult` objects.

## Phase 8: Command Chain

Goal: expose the end-to-end workflow with stable commands.

Commands:

```bash
python manage.py ingest_market_data --provider yfinance --symbols AAPL,MSFT,NVDA --timeframe 1d
python manage.py build_market_layer --layer bronze --dataset bars
python manage.py build_market_layer --layer silver --dataset bars
python manage.py build_finance_features --set technical_v1
python manage.py build_finance_features --set multifractal_v1
python manage.py build_finance_features --set tin_macd_v1
python manage.py build_finance_dataset --target forward_return_5d --split walk_forward
python manage.py quant_run_baseline --engine statsforecast
```

Acceptance:

- Command chain exists and can run on local sample data.
- Missing optional research packages fail clearly only when selected.
- No command reintroduces legacy quant naming.

## Phase 9: Documentation And Dead-Code Cleanup

Goal: remove stale docs and compatibility only after tests protect behavior.

Tasks:

- Delete outdated legacy quant docs after their active content is replaced by
  current `quant` docs.
- Delete compatibility wrappers only after imports are updated and tests pass.
- Remove files classified as `DELETE_AFTER_TESTS`.
- Keep only docs that describe current architecture, active migration steps,
  command usage, or supported safety boundaries.

Acceptance:

- Searching docs for legacy quant names returns no active docs except historical
  commit references intentionally kept.
- Root `README.md` points to the current phase plan and command chain.
- Full Django tests pass by separated module.
