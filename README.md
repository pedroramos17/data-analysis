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
