# Budget Plan

The MVP is budget-first. Local mode should cost nothing beyond the developer
machine. Cloud MVP should fit on one cheap VPS or free-tier VM.

The enforceable stack rules are documented in
[`docs/architecture/budget_first_rules.md`](../architecture/budget_first_rules.md).

## Default Limits

```text
CLOUD_MONTHLY_BUDGET_USD=25.00
CLOUD_MAX_JOB_COST_USD=2.50
CLOUD_REQUIRE_BUDGET_APPROVAL=true
```

## Cost Principles

- Prefer SQLite/local storage/DuckDB for development.
- Prefer one VPS with bundled Postgres and optional MinIO for MVP demos.
- Keep remote object storage optional and S3-compatible.
- Keep GPU work optional and manifest/planned by default.
- Avoid Kubernetes, Kafka, managed GPU, and paid vector DB in the MVP.
- Do not run cloud tests unless `ENABLE_CLOUD_TESTS=true` is explicitly set.

## Suggested Monthly Envelope

| Item | Target |
| --- | --- |
| VPS/free-tier VM | 0 to 10 USD |
| Object storage | 0 to 5 USD |
| Backups/snapshots | 0 to 5 USD |
| Domain/logging/misc | 0 to 5 USD |
| Total default guard | 25 USD |

## Operational Checks

Before enabling a cloud job, confirm:

- `python -m src.cli config show` reports expected providers.
- `CLOUD_REQUIRE_BUDGET_APPROVAL=true` unless explicitly waived.
- `CLOUD_MAX_JOB_COST_USD` is lower than the remaining monthly budget.
- Tests that can call external services are gated by `ENABLE_CLOUD_TESTS=true`.
