"""Quant4 multifractal Phase 2 preprocessing tests."""

from __future__ import annotations

import math

from django.test import SimpleTestCase


class Quant4MultifractalReturnPreprocessingTests(SimpleTestCase):
    """Return transforms and volatility preprocessing should be deterministic."""

    def test_return_transforms_are_numerically_correct(self) -> None:
        """Adjacent prices produce log, simple, absolute, and squared returns."""
        from quant4.services.multifractal.preprocessing.returns import (
            compute_return_series,
        )

        returns = compute_return_series([100.0, 105.0, 102.0])

        self.assertEqual(len(returns), 2)
        self.assertAlmostEqual(returns[0].simple_return, 0.05)
        self.assertAlmostEqual(returns[0].log_return, math.log(1.05))
        self.assertAlmostEqual(returns[1].abs_return, abs(returns[1].log_return))
        self.assertAlmostEqual(returns[1].squared_return, returns[1].log_return**2)

    def test_rolling_realized_volatility_uses_intraday_sum(self) -> None:
        """Intraday mode follows square-root sum of squared returns."""
        from quant4.services.multifractal.preprocessing.returns import (
            rolling_realized_volatility,
        )

        realized = rolling_realized_volatility([0.01, -0.02, 0.03], 3, "intraday")

        self.assertIsNone(realized[0])
        self.assertAlmostEqual(realized[-1], math.sqrt(0.01**2 + 0.02**2 + 0.03**2))

    def test_rolling_realized_volatility_daily_std_fallback(self) -> None:
        """Daily mode uses rolling standard deviation when intraday bars are absent."""
        from quant4.services.multifractal.preprocessing.returns import (
            rolling_realized_volatility,
        )

        realized = rolling_realized_volatility([0.01, 0.02, 0.03], 3, "daily")

        expected = math.sqrt(((0.01 - 0.02) ** 2 + (0.03 - 0.02) ** 2) / 3)
        self.assertAlmostEqual(realized[-1], expected)


class Quant4MultifractalWindowPreprocessingTests(SimpleTestCase):
    """Window builders should expose explicit no-leakage boundaries."""

    def test_sliding_windows_do_not_leak_future_data(self) -> None:
        """Training observations end before the horizon-aware label index."""
        from quant4.services.multifractal.preprocessing.windows import sliding_windows

        windows = sliding_windows([10.0, 11.0, 12.0, 13.0, 14.0], 3, horizon=1)

        self.assertEqual(windows[0].train_indices, [0, 1, 2])
        self.assertEqual(windows[0].label_index, 3)
        self.assertLess(windows[0].window_end, windows[0].label_timestamp)

    def test_expanding_and_anchored_walk_forward_windows_are_ordered(self) -> None:
        """Expanding and anchored walk-forward windows keep validation in the future."""
        from quant4.services.multifractal.preprocessing.windows import (
            anchored_walk_forward_windows,
            expanding_windows,
        )

        expanding = expanding_windows([1.0, 2.0, 3.0, 4.0], 2, horizon=1)
        anchored = anchored_walk_forward_windows([1.0, 2.0, 3.0, 4.0, 5.0], 3, 1)

        self.assertLess(expanding[0].window_end, expanding[0].label_timestamp)
        self.assertLess(anchored[0].window_end, anchored[0].validation_start)


class Quant4MultifractalOutlierPreprocessingTests(SimpleTestCase):
    """Robust cleaning should flag or cap values without silent deletion."""

    def test_winsorization_flags_without_default_deletion(self) -> None:
        """Outlier flags preserve row count and winsorization caps extremes."""
        from quant4.services.multifractal.preprocessing.outliers import (
            flag_zscore_outliers,
            winsorize_values,
        )

        values = [1.0, 2.0, 100.0]
        flags = flag_zscore_outliers(values, z_threshold=1.0)
        winsorized = winsorize_values(values, lower_quantile=0.0, upper_quantile=0.5)

        self.assertEqual(len(flags), len(values))
        self.assertTrue(flags[-1].is_outlier)
        self.assertEqual(len(winsorized), len(values))
        self.assertLess(winsorized[-1], values[-1])


class Quant4MultifractalSurrogatePreprocessingTests(SimpleTestCase):
    """Surrogates should be seeded and preserve requested statistical structure."""

    def test_shuffled_surrogate_preserves_distribution_not_order(self) -> None:
        """Seeded shuffled returns preserve the empirical distribution."""
        from quant4.services.multifractal.preprocessing.surrogates import (
            shuffled_returns,
        )

        values = [1.0, 2.0, 3.0, 4.0, 5.0]
        shuffled = shuffled_returns(values, seed=17)

        self.assertEqual(sorted(shuffled), values)
        self.assertNotEqual(shuffled, values)

    def test_block_shuffle_preserves_shape_and_distribution(self) -> None:
        """Block shuffling keeps length and empirical values intact."""
        from quant4.services.multifractal.preprocessing.surrogates import (
            block_shuffled_returns,
        )

        values = [1.0, 2.0, 3.0, 4.0, 5.0, 6.0]
        shuffled = block_shuffled_returns(values, block_size=2, seed=5)

        self.assertEqual(len(shuffled), len(values))
        self.assertEqual(sorted(shuffled), values)

    def test_phase_surrogate_preserves_approximate_autocorrelation(self) -> None:
        """Phase surrogate fallback keeps linear autocorrelation close."""
        from quant4.services.multifractal.preprocessing.surrogates import (
            lag_one_autocorrelation,
            phase_randomized_surrogate,
        )

        values = [1.0, 2.0, 4.0, 7.0, 11.0, 16.0]
        surrogate = phase_randomized_surrogate(values, seed=9)

        self.assertNotEqual(surrogate, values)
        self.assertAlmostEqual(
            lag_one_autocorrelation(values),
            lag_one_autocorrelation(surrogate),
            places=6,
        )

    def test_bootstrap_samples_are_seeded(self) -> None:
        """Bootstrap samples are repeatable for the same seed."""
        from quant4.services.multifractal.preprocessing.surrogates import (
            bootstrap_sample,
        )

        values = [0.1, 0.2, 0.3]

        self.assertEqual(
            bootstrap_sample(values, 6, 11),
            bootstrap_sample(values, 6, 11),
        )
