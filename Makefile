PYTHON?=python3
CONFIG?=configs/pipeline_local_mvp.yaml
RUNPOD_CONFIG?=configs/train_gpu_runpod.yaml
RUN_ID?=1
GPU_IMAGE?=data-analysis-gpu:local
COMPOSE_LOCAL=docker compose -f docker-compose.local.yml
CLOUD_ENV_FILE?=.env.cloud.example
COMPOSE_CLOUD=docker compose --env-file $(CLOUD_ENV_FILE) -f docker-compose.cloud.yml
COMPOSE_CLOUD_MVP=docker compose --env-file $(CLOUD_ENV_FILE) -f docker-compose.cloud-mvp.yml
LOCAL_SERVICE=app
CLOUD_PROFILES?=minio,scheduler
MANAGE=$(COMPOSE_LOCAL) exec $(LOCAL_SERVICE) python manage.py

.PHONY: install test smoke-test local-up local-down cloud-up cloud-down cloud-mvp-up migrate ingest-sample build-features train-baseline predict backtest risk mvp-demo mvp-demo-local pipeline-local runpod-dry-run gpu-job-dry-run cost-estimate efficiency-report gpu-image-build

install:
	$(PYTHON) -m pip install --upgrade pip
	$(PYTHON) -m pip install -r requirements.txt

test:
	$(PYTHON) -m unittest discover tests

local-up:
	$(COMPOSE_LOCAL) up -d --build $(LOCAL_SERVICE)

local-down:
	$(COMPOSE_LOCAL) down

cloud-up:
	COMPOSE_PROFILES=$(CLOUD_PROFILES) $(COMPOSE_CLOUD) up -d --build

cloud-down:
	$(COMPOSE_CLOUD) down

cloud-mvp-up:
	COMPOSE_PROFILES=$(CLOUD_PROFILES) $(COMPOSE_CLOUD_MVP) up -d --build

migrate:
	$(MANAGE) migrate
	$(COMPOSE_LOCAL) exec $(LOCAL_SERVICE) alembic -c alembic.ini upgrade head

ingest-sample:
	$(MANAGE) load_sample_sources
	$(MANAGE) ingest_sources --all --limit 5

build-features:
	$(MANAGE) compute_multifractal_features --prices 100,101,99,102,103,104

train-baseline:
	$(MANAGE) train_finance_baseline

predict:
	$(MANAGE) build_prediction_dataset --name smoke --dry-run

backtest:
	$(MANAGE) quant_run_full_experiment --name smoke-backtest --symbols SPY --timeframes 1d --backtest true --dry-run

risk:
	$(MANAGE) quant_run_risk --name smoke-risk --returns-json '[0.01,0.02,-0.01]' --prices-json '[100,102,101]' --volumes-json '[1000,1100,1050]' --data-start 2024-01-01 --data-end 2024-01-03 --split-start 2024-01-02 --split-end 2024-01-03

mvp-demo:
	$(PYTHON) -m src.cli mvp-demo --config configs/cloud_mvp.yaml

mvp-demo-local:
	APP_ENV=local DEPLOYMENT_MODE=onprem DB_MODE=sqlite STORAGE_PROVIDER=local QUEUE_PROVIDER=local COMPUTE_PROVIDER=local MODEL_DEVICE=cpu $(PYTHON) -m src.cli mvp-demo --config configs/cloud_mvp.yaml

pipeline-local:
	APP_ENV=local DEPLOYMENT_MODE=onprem DB_MODE=sqlite STORAGE_PROVIDER=local QUEUE_PROVIDER=local COMPUTE_PROVIDER=local MODEL_DEVICE=cpu $(PYTHON) -m src.cli pipeline run --config $(CONFIG)

runpod-dry-run:
	APP_ENV=cloud DEPLOYMENT_MODE=cloud_gpu COMPUTE_PROVIDER=runpod RUNPOD_DRY_RUN=true MODEL_DEVICE=cpu $(PYTHON) -m src.cli compute runpod dry-run --config $(RUNPOD_CONFIG)

gpu-job-dry-run:
	APP_ENV=cloud DEPLOYMENT_MODE=cloud_gpu DB_MODE=sqlite STORAGE_PROVIDER=local QUEUE_PROVIDER=local COMPUTE_PROVIDER=runpod MODEL_DEVICE=cpu RUNPOD_DRY_RUN=true $(PYTHON) -m src.cli gpu-job-dry-run --output exports/gpu_jobs/runpod_dry_run.json

cost-estimate:
	APP_ENV=local DEPLOYMENT_MODE=onprem DB_MODE=sqlite STORAGE_PROVIDER=local QUEUE_PROVIDER=local COMPUTE_PROVIDER=local MODEL_DEVICE=cpu $(PYTHON) -m src.cli cost estimate --config $(CONFIG)

efficiency-report:
	$(PYTHON) -m src.cli efficiency report --run-id $(RUN_ID)

gpu-image-build:
	docker build -f Dockerfile.gpu -t $(GPU_IMAGE) .

smoke-test:
	APP_ENV=local DEPLOYMENT_MODE=onprem DB_MODE=sqlite STORAGE_PROVIDER=local QUEUE_PROVIDER=local COMPUTE_PROVIDER=local MODEL_DEVICE=cpu $(PYTHON) -m src.cli config show
	APP_ENV=local DEPLOYMENT_MODE=onprem DB_MODE=sqlite STORAGE_PROVIDER=local QUEUE_PROVIDER=local COMPUTE_PROVIDER=local MODEL_DEVICE=cpu $(PYTHON) -m src.cli smoke-test
