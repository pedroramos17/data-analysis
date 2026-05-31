# Quant4

Quant4 is the local-first financial research app for this Django project. It is
the owner for shared financial metadata, reproducible run records, and artifact
pointers used by future MarketLab, risk, graph, model, backtest, portfolio, and
explainability services.

Quant4 stores operational metadata in SQLite and keeps heavy analytical data as
external artifacts referenced by URI. The MVP does not require paid APIs, GPU
libraries, cloud services, or external execution systems.

## Core Models

- `Asset`
- `MarketDataset`
- `Experiment`
- `WindowArtifact`
- `FeatureArtifact`
- `RegimeRun`
- `RiskRun`
- `LOBRun`
- `GraphSnapshot`
- `PortfolioRun`
- `ModelRun`
- `BacktestRun`
- `ExplainabilityReport`

Every run and artifact record stores:

- `config_hash`
- `random_seed`
- `data_start` and `data_end`
- `split_start` and `split_end`
- `feature_schema_json`
- `provenance_json`

## Commands

```bash
python manage.py quant4_register_assets --symbol SPY --asset-type etf
python manage.py quant4_ingest_prices --name spy-daily --source local-csv --frequency 1d
python manage.py quant4_prepare_windows --dataset-id 1 --name walk-forward-1
python manage.py quant4_detect_regimes --returns-json "[0.01,-0.02]" --prices-json "[100,98]" --data-start 2024-01-01 --data-end 2024-01-02 --split-start 2024-01-02 --split-end 2024-01-02
python manage.py quant4_run_risk --returns-json "[0.01,-0.02]" --prices-json "[100,98]" --volumes-json "[1000,1200]" --data-start 2024-01-01 --data-end 2024-01-02 --split-start 2024-01-02 --split-end 2024-01-02
python manage.py quant4_build_graphs --series-json "{\"AAA\":[[\"2024-01-01\",1],[\"2024-01-02\",2]],\"BBB\":[[\"2024-01-01\",1],[\"2024-01-02\",3]]}" --window-end 2024-01-02
python manage.py quant4_optimize_portfolio --symbols AAA,BBB --optimizer equal_weight --data-start 2024-01-01 --data-end 2024-01-31 --split-start 2024-01-31 --split-end 2024-01-31
python manage.py quant4_ingest_lob --input-path data/books.jsonl --venue-type crypto
python manage.py quant4_train_lob_model --input-path data/books.jsonl --data-start 2024-01-01 --data-end 2024-01-01 --split-start 2024-01-01 --split-end 2024-01-01
python manage.py quant4_run_full_experiment --name global_macro_quant4_v1 --symbols SPY,QQQ --timeframes 1d --no-live-trading --dry-run
```

These commands register local metadata only. Quant4 does not place orders,
connect to accounts, or provide investment advice.

## MVP 2 Risk And Regime Core

Quant4 MVP 2 adds local-only regime and risk services. Regime detectors include
rolling volatility, drawdown, return-distribution, TDA entropy fallback,
graph-density, LOB-liquidity stub, and optional `ruptures` / HMM detectors that
fail clearly when their dependencies are missing.

Risk reports separate `forecast_risk`, `portfolio_risk`, `liquidity_risk`,
`model_risk`, and `regime_risk`. Stress reports store named scenarios for 2008,
COVID, rate shock, commodity shock, FX devaluation, correlation breakdown,
liquidity freeze, and futures roll shock. These outputs are research metadata,
not execution signals.

## Graph And Topology Lab

See `docs/quant4_graphs.md` and `docs/quant4_tda.md`. Graph snapshots store
node, edge, and adjacency paths in shared `GraphSnapshot` rows so risk, regime,
and model modules can consume the same topology artifacts.

## Portfolio Optimization

See `docs/quant4_portfolio.md`. Portfolio runs store reusable weights, simulated
trades, metrics, and risk reports in shared `PortfolioRun` rows.

## LOB And Microstructure Lab

See `docs/quant4_lob.md`. LOB runs use shared `LOBRun` rows for baseline model
metrics and local artifact paths. DeepLOB and TCN-LOB remain optional PyTorch
stubs, and FX depth support depends on the venue data supplied locally.

## Full Experiment Orchestration

See `docs/quant4_full_experiment.md`. The full experiment command builds the
safe Quant4 DAG in dry-run mode by default and records skipped steps instead of
fabricating results when data or optional dependencies are unavailable.
