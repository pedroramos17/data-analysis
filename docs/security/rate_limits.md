# Rate Limits

Rate limiting protects API and job-submission endpoints, especially GPU submit. Memory rate limiting is the default; Redis is optional.

## Config

```bash
configs/rate_limits.yaml
```

```yaml
rate_limits:
  provider: memory
  anonymous:
    requests_per_minute: 20
  authenticated:
    requests_per_minute: 120
  gpu_submit:
    requests_per_hour: 3
    requests_per_day: 10
```

## Endpoint Classes

- `health` for health checks.
- `ingestion` for ingest endpoints.
- `features` for feature builds.
- `training` for local training requests.
- `gpu_submit` for RunPod submit/cancel paths.
- `predict` for inference endpoints.
- `anonymous` and `authenticated` identity-wide limits.

## Runtime

- `RATE_LIMIT_PROVIDER=memory` is default.
- `RATE_LIMIT_PROVIDER=redis` requires `RATE_LIMIT_REDIS_URL` or `REDIS_URL`.
- Heavy/write API routes also require API key auth when auth is enabled.
- GPU submit consumes stricter cost-sensitive limits.

## Verification

```bash
python3 -m src.cli smoke-test
python3 -m unittest tests.test_phase11_rate_limit
```
