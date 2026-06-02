# Multifractal Market Analysis Implementation Plan

## Repository Audit Summary

This repository is a Django project with SQLite metadata, local-first commands,
and Arrow/Parquet artifact exports. The active research app for Quant 4.0 work
is `quant4`, with models for `Asset`, `MarketDataset`, `Experiment`,
`FeatureArtifact`, `RiskRun`, `RegimeRun`, `GraphSnapshot`, `LOBRun`,
`PortfolioRun`, `ModelRun`, `BacktestRun`, and `ExplainabilityReport`.

Current relevant structure:

- `quant4/models.py`: shared SQLite metadata and run records.
- `quant4/services/`: local-first services for data foundation, windows, risk,
  regimes, graphs, MarketLab, LOB, portfolios, and full experiment orchestration.
- `quant4/management/commands/`: Django command entrypoints with
  `BaseCommand` / `CommandParser`.
- `quant4/tests/`: Django `TestCase` / `SimpleTestCase` coverage for each
  Quant4 subsystem.
- `sourceflow/finance_features/multifractal/`: existing lightweight baseline
  helpers for roughness, log returns, approximate MF-DFA, MF-DMA proxy, EMD,
  and wavelet energy.
- `monitoring/management/commands/compute_multifractal_features.py`: existing
  Sourceflow command that calls the lightweight multifractal feature builder.
- `monitoring/exporters.py` and `sourceflow/finance_ingestion/parquet_export.py`:
  existing thin PyArrow/Parquet boundaries.
- `sourceflow/config/feature_flags.py`: feature flag resolution from Django
  settings, environment, SQLite, then defaults.

Existing dependency files are `pyproject.toml` and `requirements.txt`. Required
runtime dependencies are currently Django, NetworkX, PyArrow, and Playwright.
Optional NLP dependencies already live under the `nlp` extra. Verification in
this Windows checkout should use `.\.venv-win\Scripts\python.exe`.

## Proposed Module Paths

The new system should extend Quant4 rather than introduce a duplicate top-level
`quant` package. Requested `quant/...` modules should map to:

- `quant4/services/multifractal/data/`
- `quant4/services/multifractal/preprocessing/`
- `quant4/services/multifractal/core/`
- `quant4/services/multifractal/models/`
- `quant4/services/multifractal/features/`
- `quant4/services/multifractal/risk/`
- `quant4/services/multifractal/regime/`
- `quant4/services/multifractal/portfolio/`
- `quant4/services/multifractal/lob/`
- `quant4/services/multifractal/ml/`
- `quant4/services/multifractal/reports/`
- `quant4/services/multifractal/plots/`

Management commands should follow current Django convention under
`quant4/management/commands/`, using names such as:

- `quant4_import_bars`
- `quant4_compute_returns`
- `quant4_mfdfa`
- `quant4_mf_diagnostics`
- `quant4_mf_features`
- `quant4_mf_risk`
- `quant4_mf_regime`
- `quant4_mf_portfolio`
- `quant4_mf_report`

The existing `sourceflow.finance_features.multifractal` package should remain
backward-compatible. Later phases can add adapters from Sourceflow baseline
feature payloads into Quant4 feature metadata, but should not rewrite or remove
current Sourceflow helpers.

## Dependency Additions

Phase 1 should require no new dependency beyond existing `pyarrow`, `sqlite3`,
and the Python standard library. CSV import, schema validation, metadata hashes,
and Parquet writes can be implemented with `csv`, `datetime`, `hashlib`,
`sqlite3`, and PyArrow.

Phase 3 MF-DFA can start CPU-only with standard-library numerical routines for
linear regression and small polynomial detrending. Add NumPy only if the pure
Python implementation becomes too slow or too complex, and document it as a
small required scientific dependency before adding it.

Optional later dependencies should remain behind feature flags and clear
dependency errors:

- `scipy` for robust regression, HRP enhancements, and statistical tests.
- `scikit-learn` for k-means, Gaussian mixture, and ML baselines.
- `PyWavelets` for wavelet diagnostics.
- `torch` / graph libraries for DeepLOB, TCN, GNN, and GNN/GraphRAG paths.
- `ruptures`, `hmmlearn`, or TDA libraries only as optional regime detectors.

## Data Contracts

Canonical OHLCV bars will be written to partitioned Parquet under a local root
such as `data/quant4_multifractal/bars/asset_class=<asset_class>/timeframe=<timeframe>/symbol=<symbol>/`.
The schema is:

- `symbol: str`
- `asset_class: str | null`
- `exchange: str | null`
- `timestamp: datetime`
- `open: float`
- `high: float`
- `low: float`
- `close: float`
- `volume: float | null`
- `currency: str | null`
- `source: str`
- `timeframe: str`
- `adjusted_close: float | null`

Derived returns will be written under
`data/quant4_multifractal/returns/...` with:

- `symbol`
- `timestamp`
- `timeframe`
- `return_type`
- `price_col`
- `log_return`
- `simple_return`
- `abs_return`
- `squared_return`
- `realized_volatility_optional`
- `source_dataset_id`

SQLite metadata should use a small Quant4-owned registry service first, backed
by `MarketDataset` where possible. If a dedicated registry table becomes
necessary, add a migration only after Phase 1 tests prove the existing
`MarketDataset` fields cannot represent dataset ID, schema version, partition
root, config hash, and provenance cleanly.

Dataset IDs must be deterministic hashes of normalized metadata:

- symbol set
- asset class
- exchange
- source
- timeframe
- schema version
- row count
- timestamp range
- content or config hash where available

Validation must fail clearly for duplicate timestamps, non-monotonic timestamps,
missing required prices, and zero or negative price fields. Optional fields such
as `volume`, `asset_class`, `exchange`, `currency`, and `adjusted_close` should
be preserved as nulls rather than silently filled with fake data.

## Breaking-Change Risk

The main breaking-change risk is replacing the existing Sourceflow
multifractal helpers or changing command output consumed by current tests.
Avoid this by building the research-grade implementation under Quant4 and
leaving `sourceflow.finance_features.multifractal` untouched until explicit
adapter work is added.

Other risks:

- Parquet partition paths could collide with existing `data/` artifacts. Use a
  dedicated root and never stage generated data files.
- Adding required scientific dependencies could make local tests slower or
  brittle. Keep heavy methods optional.
- MF-DFA diagnostics may be misread as predictive claims. Reports and docs must
  say these are research diagnostics, not trading signals.
- Rolling features can leak future data if window APIs are careless. All window
  builders must carry explicit `window_start`, `window_end`, and label horizon.
- LOB and intraday data availability varies by venue. Treat forex/LOB depth as
  optional and schema-driven.

## Phase Checklist

- Phase 0: commit this implementation plan after audit.
- Phase 1: add Quant4 multifractal data contracts, Parquet store, SQLite or
  `MarketDataset` registry adapter, validators, CSV importer, and returns
  generation tests.
- Phase 2: add preprocessing returns, scaling, leakage-safe windows, outlier
  flags, shuffled/block/phase/bootstrap surrogates, and tests.
- Phase 3: add production MF-DFA dataclasses, scaling diagnostics, spectrum
  extraction, summary metrics, and synthetic sanity tests.
- Phase 4: add diagnostics, shuffled/surrogate/finite-size/broad-distribution
  comparisons, bootstrap confidence intervals, attribution reports, and markdown
  output.
- Phase 5: add MF-DMA, MF-DCCA, partition-function baseline, and wavelet
  interface with optional dependencies.
- Phase 6: add MSM, MMAR, and MRW research simulation models with seeded tests.
- Phase 7: add multifractal feature matrix generation, Parquet feature store,
  rolling regime features, cross features, config hashes, and registry entries.
- Phase 8: add multifractal risk scoring, VaR variants, stress reports, and
  no-lookahead rolling risk tests.
- Phase 9: add multifractal regime detection using rolling features, simple
  change-points, optional clustering/HMM, and transition diagnostics.
- Phase 10: add portfolio optimizer integration that penalizes unstable
  multifractal risk and respects existing Quant4 portfolio constraints.
- Phase 11: add LOB multifractal interfaces over existing `quant4.services.lob`
  snapshots and synthetic LOB tests.
- Phase 12: add ML dataset builders and optional sklearn/PyTorch baselines with
  purged walk-forward evaluation.
- Phase 13: add Django CLI commands for import, returns, MF-DFA, diagnostics,
  features, risk, regime, portfolio, and reports.
- Phase 14: add matplotlib plots and markdown-first reports with config,
  dataset ID, q grid, scale range, warnings, and interpretation cautions.
- Phase 15: run and document quality gates: targeted Quant4 tests, full Django
  tests, Ruff on touched modules, migration dry-run, and no generated data in
  staged diffs.
