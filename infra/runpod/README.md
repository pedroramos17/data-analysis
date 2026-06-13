# RunPod GPU Jobs

RunPod is optional. Local SQLite/offline workflows remain the default.

## Dry Run

Plan a job without launching paid infrastructure:

```bash
python3 -m src.cli compute runpod dry-run --config configs/train_gpu_runpod.yaml
```

Dry-run forces `RUNPOD_DRY_RUN=true` inside the CLI command and never contacts the RunPod API.

## Real Submit

Real hourly pod submit requires all of the following:

- `RUNPOD_DRY_RUN=false`
- `RUNPOD_API_KEY` in the runtime environment or secret provider, never in the image
- `--confirm-cost`
- object-storage dataset, output, logs, and metrics URIs
- a positive `max_runtime_seconds`
- a positive `idle_timeout_seconds`
- an image included in `RUNPOD_ALLOWED_IMAGES`

Example:

```bash
RUNPOD_DRY_RUN=false \
RUNPOD_API_KEY=... \
RUNPOD_ALLOWED_IMAGES=ghcr.io/pedroramos17/data-analysis:latest \
python3 -m src.cli compute runpod submit --config configs/train_gpu_runpod.yaml --confirm-cost
```

## Security Defaults

- API keys are sent only as API authorization headers and are redacted from metadata/logs.
- Public Jupyter and SSH are disabled unless explicitly enabled by env and job config.
- Dataset access is expected to be read-only; artifact, log, and metric paths are write targets.
- The manifest asks for short-lived object-storage credentials when available.
- The provider rejects jobs over `RUNPOD_MAX_HOURLY_COST`, `CLOUD_MAX_JOB_COST_USD`, `RUNPOD_MAX_JOB_MINUTES`, or `RUNPOD_MAX_DATASET_SIZE_GB`.
- Dry-run manifests set `launches_paid_infrastructure=false`.

## Build Image

```bash
docker build -f Dockerfile.gpu -t ghcr.io/pedroramos17/data-analysis:latest .
```

The legacy path remains equivalent:

```bash
docker build -f infra/runpod/Dockerfile.gpu -t ghcr.io/pedroramos17/data-analysis:latest .
```

The GPU image uses a PyTorch CUDA runtime base, validates the training config
before execution, redacts secrets in logs, traps termination signals, and
best-effort uploads logs/artifacts/metrics before exiting. No API keys or object
storage credentials are baked into the image.
