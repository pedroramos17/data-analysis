"""Tests for Melao-index-inspired performance metrics."""

from __future__ import annotations

from django.test import SimpleTestCase


class MelaoMetricsTests(SimpleTestCase):
    """Risk-adjusted metrics use the full equity path."""

    def test_regression_score_is_less_endpoint_sensitive(self) -> None:
        """A late endpoint jump is discounted versus a persistent trend."""
        from sourceflow.finance_stats.melao_index import equity_log_regression_score

        steady = equity_log_regression_score([100, 102, 104, 106, 108])
        endpoint_jump = equity_log_regression_score([100, 100, 100, 100, 108])

        self.assertGreater(steady, endpoint_jump)

    def test_drawdown_duration_penalizes_slow_recovery(self) -> None:
        """Drawdown-normalized scores punish long underwater periods."""
        from sourceflow.finance_stats.melao_index import melao_inspired_score

        quick = melao_inspired_score([100, 90, 105, 108])
        slow = melao_inspired_score([100, 90, 91, 92, 108])

        self.assertGreater(quick, slow)
