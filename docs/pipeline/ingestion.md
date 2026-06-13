# Ingestion

The ingestion stage creates deterministic raw market-data partitions and metadata records. Local sample ingestion is the default, so it does not need network access, API keys, or paid services.

## Command

```bash
python3 -m src.cli ingest run --config configs/ingest_sample.yaml
```

## What It Does

- Reads symbols, asset type, timeframe, start date, and period count from config.
- Uses the sample/local source adapter unless a future provider is explicitly configured.
- Validates required OHLCV fields and timestamps.
- Normalizes timestamps to UTC.
- Deduplicates by source, asset type, symbol, timeframe, and timestamp.
- Writes raw partitions and manifests through the storage provider boundary.
- Records ingestion metadata in SQLite or Postgres depending on runtime settings.

## Local Output Layout

```text
data/lake/raw/source={source}/asset_type={asset_type}/symbol={symbol}/timeframe={timeframe}/date={YYYY-MM-DD}/part-000.parquet
data/lake/raw/source={source}/asset_type={asset_type}/symbol={symbol}/timeframe={timeframe}/date={YYYY-MM-DD}/_manifest.json
```

## Config

Use `configs/ingest_sample.yaml` for the local MVP. It is intentionally small and deterministic:

```yaml
source: sample
symbols:
  - SPY
  - QQQ
asset_type: equity
timeframe: 1d
start: "2024-01-01"
periods: 30
```

## Operational Notes

- Keep ingestion provider-neutral; business logic should not import S3, RunPod, or cloud SDKs directly.
- Keep cloud/live ingestion tests gated by explicit environment flags.
- Raw data is an audit artifact; do not overwrite it outside the storage facade.
- This pipeline is research-only and does not trigger trading or broker actions.
