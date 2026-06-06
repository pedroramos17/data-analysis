# Local Mode Runbook

Local mode is the default and requires no cloud credentials.

## Setup

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python manage.py migrate
python -m src.cli db migrate
```

On Windows PowerShell, use `.\.venv\Scripts\Activate.ps1` instead of `source`.

## Environment

```text
APP_ENV=local
DEPLOYMENT_MODE=onprem
DB_MODE=sqlite
SQLITE_PATH=./db.sqlite3
STORAGE_PROVIDER=local
DATA_LAKE_ROOT=./data/lake
OLAP_MODE=duckdb
DUCKDB_PATH=./data/lake/analytics.duckdb
MODEL_PROVIDER=local
MODEL_CACHE_DIR=./models
QUEUE_PROVIDER=local
COMPUTE_PROVIDER=local
```

## Common Commands

```bash
python -m src.cli config show
python -m src.cli smoke-test
python -m src.cli warehouse build-panel --config configs/panel.yaml
python -m src.cli features build --config configs/features.yaml
python -m src.cli mvp-demo --config configs/cloud_mvp.yaml
```

## Docker Optional

```bash
make local-up
make migrate
make smoke-test
```

Docker is optional for local development; the CLI and unit tests can run directly
from the Python environment.
