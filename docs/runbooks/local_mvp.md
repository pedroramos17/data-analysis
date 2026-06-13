# Local MVP Runbook

This runbook starts from a clean checkout and uses no paid services.

## Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
python3 -m pip install -r requirements.txt
```

## Smoke Checks

```bash
python3 -m unittest discover tests
python3 -m src.cli smoke-test
make smoke-test
```

## Run The Pipeline By Stage

```bash
python3 -m src.cli ingest run --config configs/ingest_sample.yaml
python3 -m src.cli preprocess run --config configs/preprocess_mvp.yaml
python3 -m src.cli features build --config configs/features_mvp.yaml
python3 -m src.cli windows build --config configs/sliding_window_mvp.yaml
python3 -m src.cli train run --config configs/train_baseline.yaml
python3 -m src.cli evaluate run --config configs/evaluate_mvp.yaml
```

## Run The Orchestrated Pipeline

```bash
python3 -m src.cli pipeline dry-run --config configs/pipeline_local_mvp.yaml
python3 -m src.cli pipeline run --config configs/pipeline_local_mvp.yaml
```

## Docker Local

```bash
make local-up
make smoke-test
make local-down
```

## Data Stores

- SQLite remains the default metadata database.
- Local filesystem remains the default storage provider.
- DuckDB remains the local analytical cache.
- Redis, Postgres, and MinIO are optional Docker profiles.

## Troubleshooting

- Use `python3`, not `python`, in this workspace.
- If no windows are produced, reduce `min_samples_per_window` for smoke tests or ingest more sample periods.
- If optional dependencies are missing, use the unit-test path or install `requirements.txt`.
