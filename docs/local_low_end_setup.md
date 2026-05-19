# Local Low-End Setup

Use this path for weak notebooks and safe local development.

## Install

```powershell
python -m venv .venv
.\\.venv\\Scripts\\Activate.ps1
python -m pip install -r requirements.txt
python manage.py migrate
```

## Safe Commands

```powershell
python manage.py inspect_compute --profile local_cpu_low
python manage.py load_worldmonitor_feeds
python manage.py ingest_due_sources --limit 20
python manage.py export_parquet --output exports/documents.parquet
```

Safe local work includes ingestion, normalization, Parquet exports, basic
feature store generation, small rolling stats, small MFDFA, simple signatures,
and light graph features.

## Avoid Locally

Do not run large training or full advanced pipelines on this profile:

- Mamba or NRDE training.
- Large graph embedding.
- Large batched MFDFA.
- Full-history GPU pipelines.
- Hyperparameter sweeps.

Use `cloud_student` or `cloud_serverless_on_demand` for those jobs. If you have
a strong local GPU, use `local_rtx4060ti` explicitly.

