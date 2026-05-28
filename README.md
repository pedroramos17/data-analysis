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
$env:MONITOR_ADMIN_USERNAME="admin"
$env:MONITOR_ADMIN_EMAIL="admin@example.local"
$env:MONITOR_ADMIN_PASSWORD="<choose-a-password>"
python manage.py create_admin_user
python manage.py runserver
```

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
```

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
