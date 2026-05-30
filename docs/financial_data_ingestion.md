# Financial Data Ingestion

Sourceflow finance ingestion is API-first and feature-flagged. Official connectors are preferred for SEC EDGAR, FRED, CFTC COT, exchange or broker exports, and licensed providers. Public web ingestion is disabled by default and requires explicit user permission metadata, source-specific terms notes, rate limits, attribution, and user-agent contact details.

Run examples:

```bash
python manage.py ingest_sec_edgar --cik 0000320193 --forms 10-K,10-Q --dry-run
python manage.py ingest_fred_series --series GDP --series FEDFUNDS --dry-run
python manage.py ingest_cftc_cot --report-type futures_options --dry-run
python manage.py import_financial_dataset --path data/sample.csv --dataset-type market_bars --dry-run
```

No connector is intended to bypass access controls, paywalls, anti-bot systems, or source terms.
