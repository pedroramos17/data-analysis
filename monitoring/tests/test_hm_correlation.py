"""Tests for HM-style corrected correlation."""

from __future__ import annotations

from django.test import SimpleTestCase


class HmCorrelationTests(SimpleTestCase):
    """Corrected correlations stay bounded and monotonic."""

    def test_correction_is_bounded(self) -> None:
        """Extreme inputs never exceed the Pearson correlation bounds."""
        from sourceflow.finance_stats.hm_correlation import hm_corrected_corr

        self.assertLessEqual(hm_corrected_corr(0.99, 1, 1, 0.01, 0.01), 1.0)
        self.assertGreaterEqual(hm_corrected_corr(-0.99, 1, 1, 0.01, 0.01), -1.0)

    def test_correction_is_monotonic_on_basic_fixture(self) -> None:
        """Larger observed correlations produce larger corrected correlations."""
        from sourceflow.finance_stats.hm_correlation import hm_corrected_corr

        weak = hm_corrected_corr(0.2, 1, 1, 2, 2)
        strong = hm_corrected_corr(0.5, 1, 1, 2, 2)

        self.assertLess(weak, strong)

    def test_range_restriction_strengthens_observed_correlation(self) -> None:
        """Restricted sample variance can strengthen the corrected estimate."""
        from sourceflow.finance_stats.hm_correlation import hm_corrected_corr

        corrected = hm_corrected_corr(0.4, sx=1, sy=1, sx_total=2, sy_total=2)

        self.assertGreater(corrected, 0.4)
