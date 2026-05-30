"""Explicit-permission public web report ingestion."""

from __future__ import annotations

from sourceflow.config.feature_flags import require_feature
from sourceflow.finance_ingestion.policies import (
    IngestionPolicy,
    validate_public_web_policy,
)


def ingest_public_report(url: str, policy: IngestionPolicy) -> dict[str, object]:
    """Return a compliant report ingestion envelope for an approved URL.

    Example:
        `report = ingest_public_report("https://example.test/report", policy)`
    """
    require_feature("FIN_DATA_WEB_SCRAPE_PUBLIC")
    validate_public_web_policy(policy)
    return {
        "url": url,
        "source_name": policy.source_name,
        "attribution": policy.attribution,
        "terms_notes": policy.terms_notes,
        "rate_limit_per_minute": policy.rate_limit_per_minute,
    }
