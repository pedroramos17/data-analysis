# Features

The feature stage builds versioned quant feature partitions from silver market bars. It remains local-first and writes through the storage provider boundary.

## Command

```bash
python3 -m src.cli features build --config configs/features_mvp.yaml
```

## Feature Groups

- `price_volume`
- `lob`
- `multifractal`
- `regime`
- `risk`
- `graph`

## Config

```yaml
version: mvp_v1
universe:
  - SPY
  - QQQ
start: "2024-01-01"
end: "2024-01-30"
timeframe: 1d
rolling_window: 20
long_window: 60
groups:
  - price_volume
  - regime
  - risk
require_duckdb: false
```

## Outputs

Feature outputs are partitioned by feature set, version, symbol, and timeframe:

```text
data/lake/features/feature_set={group}/version={version}/symbol={symbol}/timeframe={timeframe}/part-000.parquet
```

## Metadata

Feature runs record input URI, output URI, version, row count, column count, status, timestamps, and config JSON. SQLite remains the default metadata store; Postgres is selected only by runtime settings.

## Rules

- Add new feature groups behind config flags or registry-style functions.
- Do not import object-store SDKs in feature logic.
- Keep rolling features past-and-current only.
- Avoid profitability claims; feature outputs are research inputs.
