# RunPod Secure Hourly GPU Jobs

RunPod is optional and dry-run by default. Local SQLite/offline workflows remain available and should be used for tests and smoke runs.

## Dry Run

```bash
make runpod-dry-run
python3 -m src.cli compute runpod dry-run --config configs/train_gpu_runpod.yaml
```

Dry-run returns a `PLANNED` job and sets `launches_paid_infrastructure=false`.

## Real Submit Requirements

```bash
RUNPOD_DRY_RUN=false \
RUNPOD_API_KEY=... \
python3 -m src.cli compute runpod submit --config configs/train_gpu_runpod.yaml --confirm-cost
```

Real submit requires:

- `RUNPOD_DRY_RUN=false`.
- `RUNPOD_API_KEY` supplied at runtime, never baked into an image.
- `--confirm-cost`.
- Remote `dataset_uri`, `output_uri`, `logs_uri`, and `metrics_uri`.
- An allowed image in `RUNPOD_ALLOWED_IMAGES`.
- Runtime and idle-timeout limits.
- Passing budget guard checks.

## GPU Image

```bash
docker build -f Dockerfile.gpu -t ghcr.io/pedroramos17/data-analysis:latest .
```

The GPU image uses a PyTorch CUDA runtime base and installs only the CLI/training dependencies needed for GPU jobs. No secrets are copied into the image.

## Entrypoint Guarantees

- Validates the training config before execution.
- Runs a cost estimate before command execution.
- Redacts API keys, tokens, secrets, passwords, and credentials from logs.
- Traps `INT` and `TERM` and exits cleanly.
- Preserves the training command exit status.
- Best-effort uploads logs, artifacts, and metrics before exit.

## Security Notes

- Public Jupyter and SSH are disabled by default.
- Object-storage credentials should be short lived when possible.
- Logs and metadata must not include raw API tokens.
- Use `make cost-estimate` before enabling paid compute.
