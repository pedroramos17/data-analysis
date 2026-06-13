# Preprocessing Pipeline

Phase 4 adds deterministic raw-to-bronze/silver preprocessing under
`src/pipeline/preprocessing/`.

## Command

```bash
python -m src.cli preprocess run --config configs/preprocess.yaml
```

The command reads raw partitions from `DATA_LAKE_ROOT/raw` by default and writes:

```text
data/lake/bronze/market_bars/part-000.parquet
data/lake/silver/market_bars/part-000.parquet
data/lake/silver/market_bars/_quality_report.json
```

## Stages

- Read raw Parquet through DuckDB when available.
- Fall back only for deterministic local/mock ingestion files used in dependency-light tests.
- Clean column names and canonical types.
- Normalize timestamps to explicit UTC ISO-8601 strings.
- Sort by symbol, timeframe, and timestamp.
- Remove duplicate symbol/timeframe/timestamp rows deterministically.
- Mark and impute missing bars using previous observations only.
- Align explicit daily calendars.
- Apply corporate-action price factors if configured.
- Detect outliers and create quality flags.
- Save bronze and silver outputs through the storage provider.

## Quality Flags

- `missing_ohlcv`
- `stale_price`
- `zero_volume`
- `price_jump`
- `invalid_spread`
- `incomplete_lob`
- `timezone_adjusted`
- `imputed`

## Leakage Rules

Missing-value handling and outlier detection only use current and previous rows.
The quality report records `no_future_leakage=true`, the timestamp alignment
policy, calendar frequency, inserted row count, and output content hashes.
