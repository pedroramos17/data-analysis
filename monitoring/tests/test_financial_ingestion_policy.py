"""Tests for finance ingestion compliance policies."""

from __future__ import annotations

from django.test import SimpleTestCase, override_settings


class FinancialIngestionPolicyTests(SimpleTestCase):
    """Public web access requires explicit user permission metadata."""

    def test_public_web_policy_requires_permission(self) -> None:
        """Automated public-page ingestion fails without explicit permission."""
        from sourceflow.finance_ingestion.policies import (
            IngestionPolicy,
            validate_public_web_policy,
        )

        policy = IngestionPolicy(
            source_name="Treasury",
            source_type="public_web",
            automated_access_permitted=False,
            rate_limit_per_minute=12,
            user_agent_contact="ops@example.com",
            terms_notes="No permission recorded.",
            attribution="Treasury",
        )

        with self.assertRaisesRegex(ValueError, "automated_access_permitted=False"):
            validate_public_web_policy(policy)

    def test_public_web_policy_requires_contact_and_rate_limit(self) -> None:
        """Allowed pages still need user-agent contact and rate limits."""
        from sourceflow.finance_ingestion.policies import (
            IngestionPolicy,
            validate_public_web_policy,
        )

        policy = IngestionPolicy(
            source_name="Central bank",
            source_type="public_web",
            automated_access_permitted=True,
            rate_limit_per_minute=0,
            user_agent_contact="",
            terms_notes="Permission granted by source page.",
            attribution="Central bank",
        )

        with self.assertRaisesRegex(ValueError, "rate_limit_per_minute=0"):
            validate_public_web_policy(policy)

    @override_settings(
        SOURCEFLOW_FEATURE_FLAGS={"FIN_DATA_WEB_SCRAPE_PUBLIC": False},
    )
    def test_public_web_connector_is_flagged_off_by_default(self) -> None:
        """Public web scraping connector cannot run while disabled."""
        from sourceflow.config.feature_flags import FeatureDisabledError
        from sourceflow.finance_ingestion.connectors.public_web import (
            ingest_public_report,
        )
        from sourceflow.finance_ingestion.policies import IngestionPolicy

        policy = IngestionPolicy(
            source_name="Treasury",
            source_type="public_web",
            automated_access_permitted=True,
            rate_limit_per_minute=10,
            user_agent_contact="ops@example.com",
            terms_notes="Permission granted by source page.",
            attribution="Treasury",
        )

        with self.assertRaisesRegex(FeatureDisabledError, "FIN_DATA_WEB_SCRAPE_PUBLIC"):
            ingest_public_report("https://example.test/report", policy)
