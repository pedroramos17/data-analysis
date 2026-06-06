# Cost Minimization

Cost minimization keeps local CPU execution as the default and makes paid GPU work explicit.

## Commands

```bash
make cost-estimate
python3 -m src.cli cost estimate --config configs/pipeline_local_mvp.yaml
python3 -m src.cli cost plan --config configs/train_gpu_runpod.yaml --confirm-cost
```

## Config

```bash
configs/cost_limits.yaml
```

```yaml
cost_guard:
  max_cost_per_job_usd: 2.00
  max_daily_cost_usd: 5.00
  require_confirmation_for_paid_jobs: true
  dry_run_default: true
```

## Planner Options

- `local_cpu` for baseline and small CPU-friendly workloads.
- `local_smoke` for sampled validation before paid training.
- `runpod_gpu` for bounded GPU training.
- `runpod_batched_gpu` for batching windows when cheaper and eligible.

## Guardrails

- Monthly budget defaults to `25.00` USD.
- Per-job budget defaults to `2.50` USD.
- RunPod examples default to `0.50` USD/hour.
- Paid submit requires `--confirm-cost` and `RUNPOD_DRY_RUN=false`.
- Tests do not require paid services.

## When A Job Is Blocked

The planner returns blocked options with reasons and budget violations. Do not bypass these checks in business logic; adjust config or budget settings explicitly.
