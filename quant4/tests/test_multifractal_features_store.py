"""Quant4 multifractal Phase 7 feature engineering tests."""

from __future__ import annotations

import random
from pathlib import Path
from tempfile import TemporaryDirectory

from django.test import TestCase


class Quant4MultifractalFeatureEngineeringTests(TestCase):
    """Feature builders and stores should be local-first and reproducible."""

    def test_core_feature_row_contains_required_metrics(self) -> None:
        """Core feature rows expose H, spectrum, diagnostics, and config hash."""
        from quant4.services.multifractal.features.multifractal_features import (
            compute_multifractal_feature_row,
        )

        row = compute_multifractal_feature_row(
            "SPY",
            _seeded_returns(128, 3),
            _feature_config(),
            window_id="w0",
        )

        self.assertEqual(row["symbol"], "SPY")
        self.assertIn("hurst_h2", row)
        self.assertIn("generalized_hurst_hq", row)
        self.assertIn("delta_alpha", row)
        self.assertIn("finite_size_warning", row)
        self.assertIn("config_hash", row)

    def test_rolling_features_use_only_window_history(self) -> None:
        """Rolling feature rows record window bounds without future leakage."""
        from quant4.services.multifractal.features.multifractal_features import (
            compute_rolling_multifractal_features,
        )

        rows = compute_rolling_multifractal_features(
            "SPY",
            _seeded_returns(160, 5),
            window_size=96,
            step=32,
            config=_feature_config(),
        )

        self.assertEqual(rows[0]["window_start"], 0)
        self.assertEqual(rows[0]["window_end"], 95)
        self.assertTrue(all(row["window_start"] <= row["window_end"] for row in rows))

    def test_cross_features_include_mfdcca_metrics(self) -> None:
        """Cross features expose MF-DCCA summary and scale-specific correlations."""
        from quant4.services.multifractal.features.multifractal_features import (
            compute_cross_multifractal_features,
        )

        asset = _seeded_returns(128, 7)
        benchmark = [0.6 * value + 0.2 for value in asset]
        row = compute_cross_multifractal_features(
            "SPY",
            "SPX",
            asset,
            benchmark,
            _feature_config(),
        )

        self.assertIn("mf_dcca_corr_asset_index", row)
        self.assertIn("scale_specific_cross_corr", row)
        self.assertGreater(row["mf_dcca_corr_asset_index"], 0.0)

    def test_feature_store_writes_parquet_and_registers_artifact(self) -> None:
        """Feature matrices are stored in Parquet and indexed in SQLite."""
        from quant4.models import FeatureArtifact
        from quant4.services.multifractal.features.feature_store import (
            read_feature_matrix_parquet,
            write_feature_matrix,
        )

        rows = [
            {
                "symbol": "SPY",
                "window_id": "w0",
                "hurst_h2": 0.51,
                "delta_alpha": 0.2,
                "config_hash": "abc",
            }
        ]
        with TemporaryDirectory() as temp_dir:
            result = write_feature_matrix(
                rows,
                Path(temp_dir) / "features",
                feature_set_name="mf_core",
                config={"q_grid": [-2, 0, 2]},
            )
            loaded = read_feature_matrix_parquet(result.artifact_path)

        self.assertEqual(loaded[0]["symbol"], "SPY")
        self.assertEqual(FeatureArtifact.objects.count(), 1)
        self.assertEqual(
            FeatureArtifact.objects.first().artifact_uri,
            result.artifact_path,
        )


def _feature_config() -> object:
    from quant4.services.multifractal.core.types import MFDFAConfig

    return MFDFAConfig(
        q_grid=(-2.0, 0.0, 2.0),
        scales=(8, 16),
        min_scale_count=2,
        min_segments_per_scale=2,
    )


def _seeded_returns(length: int, seed: int) -> list[float]:
    chooser = random.Random(seed)
    return [chooser.gauss(0.0, 1.0) for _index in range(length)]
