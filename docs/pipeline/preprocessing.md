# Preprocessing

Preprocessing converts raw market partitions into bronze and silver datasets with quality diagnostics. It is designed to run locally with fallback readers when optional parquet dependencies are unavailable.

## Command

```bash
python3 -m src.cli preprocess run --config configs/preprocess_mvp.yaml
```

## What It Does

- Reads raw partitions from `data/lake/raw`.
- Writes bronze market bars to `data/lake/bronze`.
- Writes silver market bars to `data/lake/silver`.
- Normalizes timestamp alignment and reports timezone adjustments.
- Applies duplicate removal and deterministic quality checks.
- Emits a quality report with missing values, stale-price flags, price-jump flags, zero-volume flags, and corporate-action metadata.

## Config

```yaml
bronze_path: bronze/market_bars/part-000.parquet
silver_path: silver/market_bars/part-000.parquet
quality_report_path: silver/market_bars/_quality_report.json
calendar_frequency: 1d
price_jump_threshold: 0.2
stale_periods: 2
require_duckdb: false
```

## Outputs

- `data/lake/bronze/market_bars/part-000.parquet`
- `data/lake/silver/market_bars/part-000.parquet`
- `data/lake/silver/market_bars/_quality_report.json`

## Leakage Rules

- Imputation is previous-observation-only.
- No future data is used in preprocessing decisions.
- Quality flags are metadata and should not be interpreted as trading signals.
