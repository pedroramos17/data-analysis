# Autoscaling

Autoscaling is policy-first and optional. The MVP does not require always-on GPU infrastructure.

## Config

Use `configs/autoscaling.yaml` for policy defaults. Runtime settings also read environment variables such as `AUTOSCALING_ENABLED`, `AUTOSCALING_MAX_WORKERS`, `MAX_CONCURRENT_GPU_JOBS`, and `AUTOSCALING_IDLE_TIMEOUT_SECONDS`.

## Policy Inputs

- Queue depth.
- Running CPU jobs.
- Running GPU jobs.
- Maximum CPU workers.
- Maximum GPU workers.
- Hourly and daily budget limits.
- Idle timeout and scale-to-zero setting.
- Spot preference.

## Behavior

- Local mode does not autoscale by default.
- GPU jobs are bounded by max concurrent GPU jobs and cost guards.
- Small jobs should be batched or kept local when cheaper.
- Scale-to-zero is the default for optional GPU workers.

## RunPod Relationship

The autoscaler plans capacity and delegates actual GPU submission to the compute provider. It should not directly import RunPod/cloud SDKs from business logic.

## Verification

```bash
python3 -m unittest tests.test_phase10_autoscaling
python3 -m src.cli cost estimate --config configs/pipeline_gpu_runpod.yaml
```
