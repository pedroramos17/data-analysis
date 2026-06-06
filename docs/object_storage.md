# Object Storage Facade

The object storage facade is provider-neutral. Business logic should use
`src.storage.DataLakeArtifactStore` or `build_data_lake_store()` and must not
import `boto3` directly.

## Providers

- Local mode stores under `DATA_LAKE_ROOT`, which defaults to `data/lake`.
- S3-compatible mode uses the existing storage provider boundary and optional
  `boto3` dependency.
- `STORAGE_PROVIDER=s3`, `r2`, `b2`, or `minio` all use the same
  S3-compatible API and are selected through environment config.
- `OBJECT_STORAGE_ENDPOINT_URL` is optional for AWS S3 and required for most
  R2, B2, and MinIO deployments.

## Paths

`src.storage.DataLakePaths` builds keys for:

- raw data: `raw/source=.../asset_type=.../symbol=.../timeframe=.../date=.../`
- parquet datasets: `datasets/dataset=.../version=.../partition=value/`
- model artifacts: `models/model_name=.../model_version=.../`
- backtest reports: `backtests/reports/run_id=.../`
- risk reports: `risk/reports/run_id=.../`
- logs: `logs/log=.../date=.../`
- cached datasets: `cache/datasets/dataset=.../version=.../`

## Manifests

Dataset and artifact writes create `_manifest.json` beside the stored object.
Each manifest includes:

- `schema`
- `row_count`
- `source`
- `created_at`
- `content_hash`
- `dataset`
- `version`
- `partition`
- `object_path`
- `object_uri`
- `metadata`

## Usage

```python
from src.storage import build_data_lake_store

store = build_data_lake_store()
result = store.save_dataset_partition(
    "market_bars",
    "v1",
    {"symbol": "SPY", "timeframe": "1d"},
    "part-000.parquet",
    parquet_bytes,
    schema=[{"name": "close", "type": "double"}],
    row_count=100,
    source="ingest-prices",
)
```

The same code writes locally or to S3/R2/B2/MinIO depending only on runtime
environment configuration.
