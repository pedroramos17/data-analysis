# Compliance And Market Data

Allowed ingestion modes prioritize official APIs, licensed credentials, broker or exchange exports, and local files. Automated public web access is allowed only when the user has explicitly flagged permission for that source and supplied rate limits, attribution, user-agent contact, retry/backoff expectations, and source-specific terms notes.

The current implementation stores compliance metadata in `FinancialDataSource` and validates public web policies before any report ingestion envelope can be created. Real-time scraping, paywall bypass, anti-bot bypass, cookie reuse, and proxy evasion are outside the approved boundary.
