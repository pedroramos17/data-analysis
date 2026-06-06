# Data Lake And DuckDB

The analytical path is Parquet-first. Object storage is the durable artifact
boundary, while DuckDB provides local OLAP over local files or mirrored remote
prefixes.

## Layout

```text
data/lake/
  raw/source=.../asset_type=.../symbol=.../timeframe=.../date=YYYY-MM-DD/*.parquet
  bronze/
  silver/
  features/feature_set=.../version=.../symbol=.../timeframe=.../*.parquet
  gold/
  predictions/
  backtests/
  risk/
  logs/
```

Writes through `DataLakeArtifactStore` create `_manifest.json` beside dataset and
report objects. Manifests record schema, row count, source, content hash,
dataset, version, partition, object path, URI, and metadata.

## DuckDB Views

`src.warehouse.views.register_warehouse_views()` creates stable views over
available Parquet files:

| View | Purpose |
| --- | --- |
| `v_market_bars` | Canonical market bars |
| `v_returns` | Simple/log returns and return powers |
| `v_realized_volatility` | Rolling volatility windows |
| `v_multifractal_features` | Multifractional feature rows |
| `v_lob_features` | LOB feature rows/placeholders |
| `v_model_predictions` | Prediction Parquet rows |
| `v_signal_panel` | Joined bar/feature/signal panel |
| `v_backtest_panel` | Backtest panel |
| `v_risk_panel` | Risk panel |

Missing datasets become empty views with stable schemas, so partial local runs
can still compile and materialize outputs.

## Commands

```bash
python -m src.cli warehouse build-panel --config configs/panel.yaml
python -m src.cli features build --config configs/features.yaml
python -m src.cli mvp-demo --config configs/cloud_mvp.yaml
```

In cloud MVP mode, remote Parquet prefixes can be mirrored to local cache before
DuckDB scans by setting `object_store_prefixes` and `cache_root` in materializer
configs.
