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
- `provenance_json`

## Commands

```bash
python manage.py quant4_register_assets --symbol SPY --asset-type etf
python manage.py quant4_ingest_prices --name spy-daily --source local-csv --frequency 1d
python manage.py quant4_prepare_windows --dataset-id 1 --name walk-forward-1
```

These commands register local metadata only. Quant4 does not place orders,
connect to accounts, or provide investment advice.
