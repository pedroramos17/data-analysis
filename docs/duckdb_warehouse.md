# DuckDB Warehouse

The DuckDB analytical layer reads partitioned Parquet from `data/lake/` and
materializes research datasets without loading whole datasets into pandas.

## Data Lake Layout

```text
data/lake/
  raw/source=.../asset_type=.../symbol=.../timeframe=.../date=YYYY-MM-DD/*.parquet
  bronze/
  silver/
  gold/
  features/
  predictions/
  backtests/
  risk/
```

DuckDB reads local Parquet directly. In `cloud_mvp`, configure
`object_store_prefixes` so remote partitions are mirrored through the storage
provider into `cache_root` before scanning.

## Views

`src.warehouse.views.register_warehouse_views` creates these views:

- `v_market_bars`
- `v_returns`
- `v_realized_volatility`
- `v_multifractal_features`
- `v_lob_features`
- `v_model_predictions`
- `v_signal_panel`
- `v_backtest_panel`
- `v_risk_panel`

The base Parquet views tolerate missing datasets by creating empty views with a
stable schema, so local workflows can build partial panels.

## CLI

```powershell
python -m src.cli warehouse build-panel --config configs/panel.yaml
```

The CLI materializes a research panel to `output_path` from the config.

Example config:

```yaml
lake_root: data/lake
duckdb_path: data/lake/analytics.duckdb
output_path: data/lake/gold/research_panel.parquet
universe: [SPY, QQQ]
start: "2020-01-01"
end: "2030-01-01"
timeframe: 1d
cache_root: data/lake/_cache/object_store
object_store_prefixes: []
```

## Python API

```python
from src.warehouse.materialize import build_research_panel

result = build_research_panel(["SPY"], "2020-01-01", "2030-01-01", "1d")
```

Additional materializers:

- `build_training_dataset(config)`
- `build_backtest_dataset(config)`
- `materialize_feature_store(config)`

The Phase 10 feature pipeline materializes versioned feature rows with:

```powershell
python -m src.cli features build --config configs/features.yaml
```

See [Feature pipeline](feature_pipeline.md).
