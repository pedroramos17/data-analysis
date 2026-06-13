# Ingestion Pipeline

Phase 3 adds a local-first, idempotent ingestion pipeline under
`src/pipeline/ingestion/`.

## Commands

```bash
python -m src.cli ingest run --config configs/ingest.yaml
python -m src.cli ingest validate --path data/lake/raw/source=sample
```

`configs/ingest.yaml` uses deterministic mock OHLCV rows by default, so local
mode requires no network access.

## Stages

- Discover available symbols/assets from config, inline rows, or local files.
- Fetch raw market, news, or LOB rows from local/mock source adapters.
- Validate required schema fields.
- Normalize timestamps to UTC.
- Deduplicate by source, asset type, symbol, timeframe, and timestamp.
- Write raw partition files and `_manifest.json` records through the storage
  facade.
- Register each ingestion partition in SQLite/Postgres-compatible metadata.
- Record row counts, dedupe counts, missing ratio, timestamp range, output URI,
  content hash, and structured errors.

## Raw Layout

```text
data/lake/raw/
  source={source}/
  asset_type={asset_type}/
  symbol={symbol}/
  timeframe={timeframe}/
  date={YYYY-MM-DD}/
  part-000.parquet
```

PyArrow is used for real Parquet when available. In dependency-light local test
runs, the pipeline writes a deterministic fallback encoding at the same path so
repeatability, validation, hashing, and metadata registration still work without
network access.

## Metadata

`ingestion_runs` now includes explicit ingestion metadata columns:

- `source`, `asset_type`, `symbol`, `timeframe`
- `start_ts`, `end_ts`, `status`
- `rows_written`, `rows_deduplicated`, `missing_ratio`
- `output_uri`, `content_hash`
- `started_at`, `finished_at`, `error_json`

Existing `stats_json` and `error` columns remain for compatibility with earlier
MVP code.
