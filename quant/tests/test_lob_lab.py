"""Quant LOB and microstructure lab tests."""

from __future__ import annotations

import json
from io import StringIO
from pathlib import Path
from tempfile import TemporaryDirectory

from django.core.management import call_command
from django.test import TestCase, override_settings


class QuantLOBFeatureTests(TestCase):
    """LOB feature builders should be ordered and horizon-safe."""

    def test_lob_features_never_include_future_book_states(self) -> None:
        """Feature rows only use snapshots up to their own timestamp."""
        from quant.services.lob.normalizer import normalize_lob_rows
        from quant.services.lob.orderbook_features import build_orderbook_features

        snapshots = normalize_lob_rows(_book_rows(), venue_type="crypto")
        features = build_orderbook_features(snapshots, lookback=2)

        self.assertEqual(features[0].timestamp, "2024-01-01T09:30:00Z")
        self.assertNotIn("2024-01-01T09:30:02Z", features[0].source_timestamps)
        self.assertLess(
            features[0].values["mid_price"],
            features[-1].values["mid_price"],
        )

    def test_labels_are_horizon_aware(self) -> None:
        """Labels compare each row with the requested future horizon."""
        from quant.services.lob.microstructure_labels import build_lob_labels
        from quant.services.lob.normalizer import normalize_lob_rows

        snapshots = normalize_lob_rows(_book_rows(), venue_type="equity")
        labels = build_lob_labels(snapshots, horizon=2)

        self.assertEqual(labels[0].values["next_mid_movement"], 1)
        self.assertAlmostEqual(labels[0].values["h_step_return"], 0.015)
        self.assertEqual(labels[-1].values["h_step_direction"], 0)

    def test_feature_tensors_preserve_time_order(self) -> None:
        """Tensor rows stay in timestamp order after feature generation."""
        from quant.services.lob.normalizer import normalize_lob_rows
        from quant.services.lob.orderbook_features import build_feature_tensor

        snapshots = normalize_lob_rows(reversed(_book_rows()), venue_type="future")
        tensor = build_feature_tensor(snapshots)

        self.assertEqual(tensor.timestamps[0], "2024-01-01T09:30:00Z")
        self.assertLess(tensor.rows[0][0], tensor.rows[-1][0])

    def test_forex_top_of_book_format_is_optional(self) -> None:
        """FX rows can be normalized when venue depth is top-of-book only."""
        from quant.services.lob.normalizer import normalize_lob_rows

        snapshots = normalize_lob_rows([_top_book_row()], venue_type="forex")

        self.assertEqual(snapshots[0].venue_type, "forex")
        self.assertEqual(len(snapshots[0].bids), 1)


class QuantLOBModelTests(TestCase):
    """LOB baselines should stay local-first by default."""

    def test_baseline_model_runs_without_pytorch(self) -> None:
        """The imbalance baseline predicts without importing torch."""
        from quant.services.lob.deeplob import NaiveImbalanceBaseline

        model = NaiveImbalanceBaseline(threshold=0.10)
        predictions = model.predict(
            [{"order_imbalance": 0.2}, {"order_imbalance": -0.2}]
        )

        self.assertEqual(predictions, [1, -1])

    @override_settings(
        SOURCEFLOW_FEATURE_FLAGS={
            "QUANT_LOB_DEEPLOB": True,
            "QUANT_LOB_TCN": True,
        }
    )
    def test_optional_lob_models_fail_clearly_without_pytorch(self) -> None:
        """DeepLOB and TCN-LOB stubs name the missing PyTorch dependency."""
        from quant.services.lob.deeplob import DeepLOBModel, TCNLOBModel
        from quant.services.registry import OptionalDependencyMissingError

        with self.assertRaisesRegex(OptionalDependencyMissingError, "torch"):
            DeepLOBModel(required_module="missing_quant_torch").fit()
        with self.assertRaisesRegex(OptionalDependencyMissingError, "torch"):
            TCNLOBModel(required_module="missing_quant_torch").fit()

    def test_lob_run_stores_metrics_and_artifact_paths(self) -> None:
        """The train command persists metrics and local artifact paths."""
        from quant.models import LOBRun

        with TemporaryDirectory() as output_dir:
            input_path = Path(output_dir) / "lob.jsonl"
            _write_jsonl(input_path, _book_rows())
            call_command(
                "quant_train_lob_model",
                "--name",
                "lob-smoke",
                "--input-path",
                str(input_path),
                "--output-dir",
                output_dir,
                "--data-start",
                "2024-01-01",
                "--data-end",
                "2024-01-01",
                "--split-start",
                "2024-01-01",
                "--split-end",
                "2024-01-01",
                stdout=StringIO(),
            )
            run = LOBRun.objects.get(name="lob-smoke")

        self.assertIn("accuracy", run.metrics_json)
        self.assertIn("artifact_paths", run.metrics_json)
        self.assertTrue(run.artifact_uri.endswith("lob-smoke_lob_metrics.json"))


def _book_rows() -> list[dict[str, object]]:
    return [
        _book_row("2024-01-01T09:30:00Z", 99.0, 101.0, 120.0, 80.0),
        _book_row("2024-01-01T09:30:01Z", 100.0, 102.0, 100.0, 90.0),
        _book_row("2024-01-01T09:30:02Z", 100.5, 102.5, 80.0, 120.0),
    ]


def _book_row(
    timestamp: str,
    bid: float,
    ask: float,
    bid_size: float,
    ask_size: float,
) -> dict[str, object]:
    return {
        "timestamp": timestamp,
        "symbol": "BTC-USD",
        "bids": [[bid, bid_size], [bid - 1.0, bid_size / 2.0]],
        "asks": [[ask, ask_size], [ask + 1.0, ask_size / 2.0]],
    }


def _top_book_row() -> dict[str, object]:
    return {
        "timestamp": "2024-01-01T09:30:00Z",
        "symbol": "EURUSD",
        "bid": 1.1000,
        "ask": 1.1002,
        "bid_size": 1_000_000,
        "ask_size": 900_000,
    }


def _write_jsonl(path: Path, rows: list[dict[str, object]]) -> None:
    payload = "\n".join(json.dumps(row, sort_keys=True) for row in rows)
    path.write_text(f"{payload}\n", encoding="utf-8")
