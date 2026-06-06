# Gaps For Cloud Pipeline

This audit identifies where cloud/on-prem runtime modes should be injected after
the current pipeline map. The goal is cheap local execution first, with secure
hourly RunPod GPU execution only for heavy training or batch inference jobs.

## Existing Storage Assumptions

- Local mode assumes SQLite for metadata and local filesystem paths for data lake,
  model cache, reports, logs, and exports.
- DuckDB scans local or mirrored Parquet; object-store prefixes are mirrored to a
  local cache before analytical SQL.
- Older Quant4 and Sourceflow readers often read local files directly and should
  remain valid.
- Cloud mode should inject storage only through `src.storage` and provider
  registry boundaries, not by adding SDK imports to research modules.

## Where Cloud Mode Should Be Injected

| Boundary | Existing module | Required injection |
| --- | --- | --- |
| Runtime config | `src.config.settings` | Add explicit `cloud_gpu`, RunPod, orchestrator, rate-limit, device, efficiency, security, and cost-guard settings. |
| Compute | `src.providers.compute` | Add RunPod dry-run/manifest provider first; real launch/terminate later behind the same interface. |
| Queue | `src.providers.queue` | Keep local default; Redis only when explicitly selected. |
| Rate limit | `monitoring.fetchers.rate_limit` | Add a provider facade before multi-worker cloud ingestion; current memory limiter is local only. |
| Orchestration | `monitoring/orchestration`, `src.api.jobs` | Keep local orchestration default; represent APScheduler/Prefect/Dagster as optional providers/settings first. |
| Storage | `src.storage`, `src.providers.storage` | Use local by default; object storage only for configured cloud datasets/models. |
| Metadata DB | Django settings and `src.database.core_schema` | Keep SQLite default; allow Postgres only when configured. |
| Model device | `src.models`, `src.api.handlers` | CPU by default; CUDA/auto only as explicit model runtime metadata. |
| Security | `monitoring.orchestration.command_validation` | Reuse shell-operator and denied-command checks for any launcher. |
| Efficiency | new settings/future measurement hooks | Record dry-run code/runtime estimates before optimizing. |

## Modules Needing Provider Abstraction

- RunPod compute execution needs a `src.providers.compute.runpod` facade.
- Rate limiting now has memory and Redis provider implementations; future work is
  to apply it consistently across every multi-worker ingestion path.
- Orchestration needs a small provider boundary for local, APScheduler, Prefect,
  and Dagster before external schedulers are introduced.
- Autoscaling should start as settings and dry-run job metadata, then become a
  provider-managed scaling policy.
- Code-efficiency measurement should start as config/provenance fields and later
  wrap training/backtest stages with timing, memory, row-count, and artifact-size
  metrics.

## What Should Remain Untouched

- SQLite mode and existing Django migrations.
- Local/on-prem CLI/API workflows.
- Existing Sourceflow ingestion policy checks and rate-limit semantics.
- Quant4 no-live-trading behavior.
- Existing DuckDB/Parquet outputs and compatibility schema.
- Local Docker Compose stack defaults.

## Cloud GPU Rules

- RunPod is optional and must be selected explicitly with `COMPUTE_PROVIDER=runpod`
  and `DEPLOYMENT_MODE=cloud_gpu`.
- The API server stays CPU-oriented; GPU pods are for training and batch inference
  only.
- Dry-run job specs must not launch pods or require paid credentials.
- Real pods must be hourly/ephemeral, started only when needed, and terminated
  after job completion or timeout.
- A missing RunPod API key must block real execution, not local dry-runs.

## Closed Phase 1-2 Gaps

- `src.config.settings` exposes `cloud_gpu`, RunPod, orchestrator, rate-limit,
  model-device, cost-mode, autoscaling, efficiency, and security settings.
- Provider provenance records these settings without secrets.
- `make mvp-demo-local` and `make gpu-job-dry-run` exist.
- `COMPUTE_PROVIDER=runpod` resolves to a dedicated dry-run provider by default.
- `COMPUTE_PROVIDER=stub` resolves to a generic dry-run provider.
- Storage, queue, compute, and rate-limit provider contracts have Phase 2
  dependency-light tests.

## Remaining Gaps

- Real RunPod launch, log streaming, and termination are still intentionally not
  implemented; dry-run manifests remain the safe default.
- Orchestration providers for APScheduler, Prefect, and Dagster are still only
  settings boundaries.
- Rate limiting still needs to be applied to every ingestion/API path that can run
  concurrently in cloud mode.
