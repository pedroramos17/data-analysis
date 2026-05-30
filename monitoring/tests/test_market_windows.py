"""Tests for global market window assignment."""

from __future__ import annotations

from datetime import UTC, datetime

from django.test import SimpleTestCase, override_settings


class MarketWindowTests(SimpleTestCase):
    """Exchange windows map UTC timestamps to local sessions."""

    def test_assigns_regular_nyse_session(self) -> None:
        """NYSE regular hours are detected from UTC timestamps."""
        from sourceflow.finance_ingestion.global_market_windows import (
            assign_market_session,
        )

        session = assign_market_session(datetime(2026, 1, 5, 15, 0, tzinfo=UTC), "NYSE")

        self.assertEqual(session["exchange"], "NYSE")
        self.assertEqual(session["session_type"], "regular")
        self.assertEqual(session["local_date"], "2026-01-05")

    @override_settings(
        SOURCEFLOW_FEATURE_FLAGS={"FIN_DATA_GLOBAL_MARKET_WINDOWS": False},
    )
    def test_market_windows_are_flag_guarded(self) -> None:
        """Session assignment fails when the market-window flag is disabled."""
        from sourceflow.config.feature_flags import FeatureDisabledError
        from sourceflow.finance_ingestion.global_market_windows import (
            assign_market_session,
        )

        with self.assertRaisesRegex(
            FeatureDisabledError, "FIN_DATA_GLOBAL_MARKET_WINDOWS"
        ):
            assign_market_session(datetime(2026, 1, 5, 15, 0, tzinfo=UTC), "NYSE")
