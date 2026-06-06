# Budget-First Architecture Rules

The MVP must stay cheap by default while leaving clear seams for future
production upgrades. These rules are architectural constraints, not suggestions.

## MVP Cheapest Stack

The accepted MVP stack is:

| Boundary | Required MVP choice |
| --- | --- |
| Host | one cheap VPS or free-tier VM |
| Orchestration | Docker Compose |
| Transactional DB | small Postgres instance/container, with SQLite retained locally |
| OLAP | embedded DuckDB |
| Object storage | S3-compatible storage such as MinIO, R2, B2, or S3 |
| Inference | CPU inference by default |
| GPU | optional only for batch training jobs |
| Observability | health checks, logs, and lightweight metrics only |

## Explicitly Out Of MVP Scope

Do not add these as required MVP components:

- Kubernetes,
- Kafka,
- Spark,
- managed vector database,
- always-on GPU,
- expensive observability stack,
- live trading or broker execution.

## Future Upgrade Path

The architecture should support future production without making MVP expensive:

| MVP boundary | Future path |
| --- | --- |
| local queue | Redis, RabbitMQ, or SQS |
| local object storage | Cloudflare R2, Backblaze B2, or AWS S3 |
| Postgres single node/container | managed Postgres |
| DuckDB local cache | MotherDuck, BigQuery, or Snowflake later if needed |
| cron/simple scheduler | Airflow, Prefect, or Dagster later |
| CPU batch | GPU batch provider |
| SQLite | retained for edge, on-premise, and offline mode |

## Enforcement

Budget-first rules are enforced by documentation and tests:

- Docker Compose manifests must not include forbidden MVP infrastructure.
- Runtime defaults must keep local mode cheap: SQLite, local storage, DuckDB,
  local queue, local model registry, CPU/local compute.
- Cloud MVP examples must keep GPU disabled by default.
- Cloud GPU examples must stay dry-run by default and must not launch paid
  infrastructure without explicit credentials and future provider implementation.
- Cloud connectivity tests must skip unless `ENABLE_CLOUD_TESTS=true`.
- Optional providers must stay behind provider boundaries and fail clearly when
  optional dependencies are missing.

## Acceptance

The architecture is acceptable when it supports a path to production upgrades but
the default MVP can still run cheaply on one small VM or locally without paid
services.
