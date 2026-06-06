# Final Acceptance Checklist

Phase 22 closes the local-first quant ML MVP with dependency-light evidence. The
checks below are designed to run without paid services, cloud credentials, Docker
runtime dependencies, Postgres, Redis, SQLAlchemy, DuckDB, PyArrow, PyYAML,
pytest, FastAPI, or GPU access unless explicitly noted.

No live trading: the MVP remains research-only. It supports forecasting, risk assessment,
backtesting, and portfolio analytics. It does not include live trading, broker
connectivity, order placement, or execution adapters.

## Refresh Commands

```bash
make smoke-test
make pipeline-local
python3 -m src.cli efficiency report --run-id <run_id>
make runpod-dry-run
make cost-estimate
docker compose -f docker-compose.local.yml config
docker compose -f docker-compose.cloud.yml config
python3 -m unittest discover tests
python3 -m compileall src tests
git diff --check
```

Observed Phase 22 local evidence: `make pipeline-local` completed with pipeline
run id `5` and wrote `reports/efficiency/pipeline_run_5.json` plus Markdown.
RunPod real submit was intentionally not executed because paid jobs require
`RUNPOD_DRY_RUN=false`, `RUNPOD_API_KEY`, remote artifact URIs, and
`--confirm-cost`.

## Acceptance Criteria

- [x] AC-01: Local-first defaults remain intact: SQLite, local filesystem, local queue, local model cache, CPU execution, and no paid API requirement. Evidence: `src/config/settings.py`, `.env.example`, `configs/pipeline_local_mvp.yaml`, `make smoke-test`.
- [x] AC-02: Provider selection stays behind `ProviderRegistry`; optional Postgres, S3-compatible storage, Redis, and RunPod can be selected without changing business logic. Evidence: `src/providers/registry.py`, `src/providers/`, provider facade tests.
- [x] AC-03: Ingestion supports sample/local market data, validation, dedupe, raw lake layout, and metadata registration. Evidence: `src/pipeline/ingestion/`, `configs/ingest_sample.yaml`, `tests/test_phase3_ingestion.py`.
- [x] AC-04: Preprocessing writes bronze/silver outputs, normalizes timestamps, aligns calendars, tracks quality flags, and records no-future-leakage metadata. Evidence: `src/pipeline/preprocessing/`, `configs/preprocess_mvp.yaml`, `tests/test_phase4_preprocessing.py`.
- [x] AC-05: Feature extraction writes versioned feature sets and keeps rolling calculations past/current-row only. Evidence: `src/pipeline/features/`, `configs/features_mvp.yaml`, `tests/test_phase5_feature_extraction.py`.
- [x] AC-06: Sliding windows support rolling train/validation/test splits with purge and embargo; production-like and smoke-sized examples are both present. Evidence: `configs/sliding_window_mvp.yaml`, `configs/pipeline_local_mvp.yaml`, `tests/test_phase6_sliding_window.py`.
- [x] AC-07: Local baseline training and prediction produce model and prediction artifacts without GPU or cloud dependencies. Evidence: `src/pipeline/training/`, `configs/train_baseline.yaml`, `tests/test_phase7_training_pipeline.py`, `make pipeline-local`.
- [x] AC-08: Fin-Mamba and SAMBA remain optional; local small configs are CPU-oriented and RunPod GPU training is opt-in. Evidence: `configs/train_fin_mamba_small.yaml`, `configs/train_samba_small.yaml`, `configs/train_gpu_runpod.yaml`, sequence-model tests.
- [x] AC-09: Evaluation, backtesting, risk, and aggregate reporting are wired into the local pipeline. Evidence: `src/pipeline/evaluation/`, `configs/evaluate_mvp.yaml`, `configs/backtest_mvp.yaml`, pipeline artifacts under `data/lake/pipeline_runs/`.
- [x] AC-10: Orchestration persists run/task state, retries, statuses, artifacts, and API/CLI operations return `run_id` instead of blocking indefinitely. Evidence: `src/orchestration/`, `src/api/handlers.py`, `src/cli.py`, `tests/test_phase12_orchestration.py`, `tests/test_phase16_api_endpoints.py`.
- [x] AC-11: RunPod defaults to dry-run and real paid submit is blocked unless credentials, remote artifact URIs, and `--confirm-cost` are present. Evidence: `src/providers/compute/runpod.py`, `src/pipeline/training/runpod_job.py`, `configs/train_gpu_runpod.yaml`, `make runpod-dry-run`.
- [x] AC-12: GPU jobs carry timeout, idle timeout, cost guard, artifact/log/metric return paths, and remote termination controls. Evidence: `configs/train_gpu_runpod.yaml`, `infra/runpod/entrypoint_train.sh`, `docs/cloud/runpod_secure_hourly.md`, RunPod provider tests.
- [x] AC-13: Cost planning and budget gates run before paid compute and keep local pipeline cost at zero. Evidence: `src/cost/`, `configs/cost_limits.yaml`, `configs/pipeline_local_mvp.yaml`, `make cost-estimate`, `tests/test_phase14_cost_planning.py`.
- [x] AC-14: Heavy/write API endpoints require auth when enabled, GPU submit is rate-limited, and secrets are redacted from logs, reports, CLI output, metadata, and audit events. Evidence: `src/security/`, `src/middleware/rate_limit.py`, `tests/test_phase11_rate_limit.py`, `tests/test_phase15_security_hardening.py`.
- [x] AC-15: Docker and Compose assets support local app execution and cloud deployment while keeping RunPod external. Evidence: `Dockerfile`, `Dockerfile.gpu`, `docker-compose.local.yml`, `docker-compose.cloud.yml`, `.env.runpod.example`, `tests/test_phase19_docker_deployment.py`.
- [x] AC-16: Efficiency profiling records per-task wall time, CPU time, memory, throughput, cost proxies, quality gates, JSON reports, and Markdown reports. Evidence: `src/observability/efficiency/`, `reports/efficiency/`, `python3 -m src.cli efficiency report --run-id <run_id>`, `tests/test_phase13_efficiency.py`.
- [x] AC-17: Documentation covers the full local pipeline, RunPod secure hourly flow, autoscaling, rate limits, cost minimization, efficiency reports, runbooks, limitations, and no-live-trading boundary. Evidence: `README.md`, `docs/pipeline/`, `docs/cloud/`, `docs/security/`, `docs/cost/`, `docs/observability/`, `docs/runbooks/`, `python3 -m unittest discover tests`.

## Known Non-Goals

- Real RunPod submit and termination were not live-tested without credentials and explicit cost confirmation.
- Optional dependency-backed paths may skip or use fallbacks when SQLAlchemy, DuckDB, PyArrow, PyTorch, FastAPI, or Docker are unavailable.
- Live trading execution remains out of scope.
