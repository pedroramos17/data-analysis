# GPU Training On RunPod Runbook

RunPod GPU training is optional. Dry-run first, estimate cost second, and only then submit a paid job with explicit confirmation.

## Dry Run

```bash
make runpod-dry-run
python3 -m src.cli compute runpod dry-run --config configs/train_gpu_runpod.yaml
```

Expected result:

```json
{
  "status": "PLANNED",
  "metadata": {
    "dry_run": true,
    "launches_paid_infrastructure": false
  }
}
```

## Build GPU Image

```bash
docker build -f Dockerfile.gpu -t ghcr.io/pedroramos17/data-analysis:latest .
```

## Configure Runtime Secrets

```bash
cp .env.runpod.example .env.runpod
```

Edit `.env.runpod` outside version control. Keep `RUNPOD_DRY_RUN=true` until all artifact paths and budgets are verified.

## Cost Plan

```bash
python3 -m src.cli cost plan --config configs/train_gpu_runpod.yaml --confirm-cost
```

## Real Submit

```bash
RUNPOD_DRY_RUN=false \
RUNPOD_API_KEY=... \
python3 -m src.cli compute runpod submit --config configs/train_gpu_runpod.yaml --confirm-cost
```

## Required Remote Paths

- `dataset_uri`
- `output_uri`
- `logs_uri`
- `metrics_uri`

## Cleanup And Monitoring

```bash
python3 -m src.cli compute runpod status --job-id <job-id>
python3 -m src.cli compute runpod logs --job-id <job-id>
python3 -m src.cli compute runpod cancel --job-id <job-id>
python3 -m src.cli compute runpod cleanup-idle
```

## Safety Checklist

- Confirm `RUNPOD_DRY_RUN=false` only for the final paid submit.
- Confirm `--confirm-cost` is present.
- Confirm the hourly cost is within `RUNPOD_MAX_HOURLY_COST`.
- Confirm artifact/log/metric URIs are remote and writable.
- Confirm API keys are only in runtime environment or secret provider.
- Confirm public Jupyter and SSH remain disabled unless explicitly required.
