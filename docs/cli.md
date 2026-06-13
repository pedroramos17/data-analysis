# CLI Commands

The CLI exposes core MVP workflows without starting the API server.
Commands use runtime settings and provider registry boundaries, so local SQLite
and cloud Postgres/object storage are selected by environment, not command code.

## Commands

```powershell
python -m src.cli config show
python -m src.cli db migrate
python -m src.cli ingest run --config configs/ingest.yaml
python -m src.cli ingest validate --path data/lake/raw/source=sample
python -m src.cli preprocess run --config configs/preprocess.yaml
python -m src.cli features build --config configs/features.yaml
python -m src.cli warehouse build-panel --config configs/panel.yaml
python -m src.cli model train --config configs/model.yaml
python -m src.cli model predict --config configs/predict.yaml
python -m src.cli backtest run --config configs/backtest.yaml
python -m src.cli risk run --config configs/risk.yaml
python -m src.cli mvp-demo --config configs/cloud_mvp.yaml
python -m src.cli storage sync --from local --to object
python -m src.cli smoke-test
```

The one-command local/cloud-compatible MVP path is also available as:

```powershell
make mvp-demo
```

`features build-store` remains as a compatibility alias for earlier configs.

`ingest run` executes the local-first ingestion pipeline and records metadata in
SQLite/Postgres. `preprocess run` deterministically writes bronze/silver outputs
and a quality report. Backtest and risk jobs are queued/planned by default. Small
model train/predict examples use `sync: true` in their YAML files.
The `mvp-demo` command executes the sample ingest, raw Parquet write,
compatibility DB registration, DuckDB panel/features, baseline train, optional
sequence-model metadata, batch prediction, signal persistence, backtest, risk,
alpha-validation diagnostics, and report export pipeline in one process. It
requires SQLAlchemy, DuckDB, PyArrow, and PyYAML from the project requirements.
Persisted signals include `explanation_json` with the Phase 14 XAI envelope.

For object storage syncs, configure `STORAGE_PROVIDER=s3|r2|b2|minio`,
`OBJECT_STORAGE_BUCKET`, access key, secret key, and optional endpoint URL. The
CLI reports those missing credential requirements directly when remote storage
is requested without a configured object provider.
