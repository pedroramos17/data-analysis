# Public Source Monitor

A small Django project for collecting public news, trends, papers, security
advisories, and other open-web data from RSS feeds, HTML pages, sitemaps, and
approved APIs.

The ingestion flow stores raw snapshots first, normalizes parsed records second,
and exports analytical datasets to Apache Arrow / Parquet. SQLite holds source
metadata, checkpoints, job status, review queues, and the normalized browse
index.

## Setup

```powershell
python -m venv .venv
.\\.venv\\Scripts\\Activate.ps1
python -m pip install -r requirements.txt
python -m playwright install chromium
python manage.py migrate
python manage.py load_worldmonitor_feeds
python manage.py seed_dev_admin --show-credentials
python manage.py runserver 127.0.0.1:8000 --noreload
```

## Development Admin User

For local development, create a Django admin user with an idempotent seed:

```powershell
python manage.py migrate
python manage.py seed_dev_admin --show-credentials
```

Default local credentials are enabled only while `DEBUG=True`:

```text
URL: http://127.0.0.1:8000/admin/
username: admin
password: admin12345
```

Override credentials with `DEV_ADMIN_USERNAME`, `DEV_ADMIN_EMAIL`, and
`DEV_ADMIN_PASSWORD`, or pass `--username`, `--email`, and `--password`. The
command refuses non-debug environments unless `--allow-production` is passed,
and production mode never accepts the fallback password.

The older `create_admin_user` command remains available for deployments that
already use `MONITOR_ADMIN_*` variables.

## Common Commands

```powershell
python manage.py test
python manage.py load_worldmonitor_feeds
python manage.py add_google_news_topic --query "AI chips" --category technology --tags ai,chips
python manage.py ingest_due_sources --limit 20
python manage.py ingest_source --source-id 1 --limit 50
python manage.py build_daily_digest
python manage.py enrich_documents --limit 500
python manage.py discover_sources --limit 200
python manage.py evaluate_alerts --lookback-hours 24
python manage.py cluster_topics --window-hours 72 --min-documents 3
python manage.py score_source_reputation --window-days 30
python manage.py export_parquet --output exports\\documents.parquet
python manage.py inspect_compute --profile local_cpu_low
python manage.py create_dashboard_jobs --template local_simple_pipeline --profile local_cpu_low
python manage.py dashboard_worker --profile local_cpu_low --worker-id cpu-1
```

## Comparison Machine Philosophy

Sourceflow is a comparison machine, not a truth machine. It does not decide
which article is true, label sources as biased, or infer hidden intent. Its job
is to make differences in coverage visible, measurable, and explainable.

The comparison pipeline groups feeds under providers and owners, clusters
articles into event groups, extracts local entity and claim candidates, and
compares coverage across sources, providers, and owners. Omission detection is
comparative: it can say that a provider covered an event but did not mention a
claim or entity that appeared in comparable coverage. It should not say that a
provider hid the truth.

Local deterministic backends are the default so the MVP can run on SQLite and
Parquet without heavy infrastructure:

```powershell
python manage.py ingest_rss --limit 50
python manage.py enrich_articles --limit 500
python manage.py cluster_events --window-hours 72
python manage.py compare_events --limit 100
python manage.py export_parquet --dataset all --output-dir exports
```

The first Parquet datasets for analytical workloads are `articles`, `entities`,
`claims`, `events`, `article_event_links`, `event_coverage`, and
`event_comparison_snapshots`.

## Compute Profiles

The project separates safe local work from advanced GPU/cloud work. Use
`local_cpu_low` for weak notebooks, `local_mx350_queue` only for micro-batch
GPU smoke tests, `local_rtx4060ti` for strong local GPU runs, and
`cloud_student` or `cloud_serverless_on_demand` for large partitioned jobs.

See:

- [Compute profiles](docs/compute_profiles.md)
- [Low-end local setup](docs/local_low_end_setup.md)
- [Cloud student setup](docs/cloud_student_setup.md)
- [Control dashboard](docs/control_dashboard.md)

## Finance And Quant Refactor

The active finance refactor plan is
[`docs/finance_quant_refactor_phases.md`](docs/finance_quant_refactor_phases.md).
It defines the hard `finance_core`, `warehouse`, `finance_ingestion`,
`finance_dataset`, `finance_features`, and `quant` boundaries. It also records
the breaking decision that the legacy quant app name is now `quant` everywhere
and old local SQLite data from that app is not preserved.

## Control Dashboard

The multi-profile control dashboard is available at:

```text
http://127.0.0.1:8000/dashboard/
```

It manages SQLite-backed `PipelineJob` rows, local workers, resource locks,
resource snapshots, cloud budget policies, usage estimates, logs, manifests,
and generated artifacts. It does not require Celery, Redis, PyTorch, CuPy, or
cloud SDKs.

Start workers from separate terminals:

```powershell
python manage.py dashboard_worker --profile local_cpu_low --worker-id cpu-1
python manage.py dashboard_worker --profile local_mx350_queue --worker-id mx350-1
python manage.py dashboard_worker --profile local_rtx4060ti --worker-id gpu-1
```

Create jobs from safe templates:

```powershell
python manage.py create_dashboard_jobs --template local_simple_pipeline --profile local_cpu_low
python manage.py create_dashboard_jobs --template cloud_student_advanced_plan --profile cloud_student --dry-run
```

Cloud jobs are manifest-based and provider-neutral. They are blocked by a
budget policy and, by default, remain `waiting_approval` until explicitly
approved:

```powershell
python manage.py cloud_budget_summary
python manage.py approve_cloud_job --job-id 123 --approved-by local-admin
python manage.py block_cloud_job --job-id 123 --reason "over budget"
```

Operating concept: local CPU validates data and simple features; MX350 runs
only micro-batches; RTX accelerates bounded local GPU work; cloud profiles
scale partitioned advanced jobs with budget guards.

## CI/CD Patterns

GitHub Actions workflows live in `.github/workflows/`:

- `ci.yml` runs Django checks, migration drift checks, migrations, tests, and
  lightweight dashboard/compute smoke checks on pushes and pull requests.
- `release-preview.yml` is a manual `workflow_dispatch` preview that validates
  the project and uploads a small diagnostic artifact without deploying or
  running cloud jobs.

The workflows install only the lightweight core requirements. Provider SDKs,
PyTorch, CuPy, Celery, Redis, and cloud execution remain optional.

## Safety Boundaries

- The crawler checks `robots.txt` before HTTP or browser fetches.
- Browser fetches are limited to public pages that need JavaScript rendering.
- The project does not bypass logins, paywalls, anti-bot systems, or access
  controls.
- Retries use bounded exponential backoff, failed records go to a dead-letter
  table, and writes are idempotent through source-scoped and global hashes.
- RSS feeds load from `monitoring/catalogs/worldmonitor_feeds.json` and are
  validated against `monitoring/catalogs/rss_allowed_domains.json`.
- The digest API is available at `/api/news/v1/list-feed-digest/`; the browser
  digest page is `/digest/`.
- Phase 2 intelligence runs locally: enrichment, source discovery candidates,
  in-app alert rules, deterministic topic clusters, canonical URL references,
  and source reputation snapshots. Alert review is available at `/alerts/` and
  topic clusters are available at `/topics/`.

## Symbolic Factor Mining

Sourceflow includes a local Symbolic Factor Mining subsystem for source
intelligence comparison and propagation analysis. It stores typed formula
metadata, dependencies, evaluations, and run records in SQLite, while
materialized factor values remain Parquet-first under `exports/factors/`.
The subsystem avoids truth judgments and explains signals as coverage
asymmetry, provider concentration, framing divergence, evidence density, claim
disagreement, possible omission, and amplification patterns.

Example commands:

```powershell
python manage.py init_factor_base
python manage.py register_seed_factors
python manage.py compute_factors --as-of 2026-05-28T12:00:00Z
python manage.py search_symbolic_factors --method random --n 500 --max-depth 4 --objective future_event_growth --window 7d
python manage.py search_symbolic_factors --method gp --population 100 --generations 20 --objective future_claim_conflict --max-depth 5
python manage.py evaluate_factors --factor coverage_intensity --objective future_event_growth
python manage.py explain_factor_score --factor coverage_intensity --entity-id event:1
python manage.py build_graphrag_context --recent 100
```

Example formula JSON:

```json
{
  "kind": "binary",
  "name": "div_safe",
  "left": {"kind": "operand", "name": "article_count", "return_type": "numeric"},
  "right": {"kind": "constant", "value": 1.0, "return_type": "numeric"}
}
```

Example GraphRAG context output:

```json
{
  "event_id": 42,
  "event_title": "Example event",
  "top_sources": ["Source A", "Source B"],
  "top_providers": ["Provider A"],
  "top_factor_scores": [
    {
      "name": "coverage_intensity",
      "explanation": "Compares coverage by one source against peer coverage for the same event."
    }
  ]
}
```
