"""Tests for the Phase 7 forecast model layer."""

from __future__ import annotations

import json
import tempfile
import unittest
from datetime import datetime
from pathlib import Path

from src.models.baselines import NaiveReturnBaseline, RidgeReturnBaseline
from src.models.base import MissingModelCheckpointError
from src.models.explainability import SIGNAL_EXPLANATION_FIELDS
from src.models.inference.batch_predict import prediction_rows, signal_row
from src.models.inference.online_predict import OnlinePredictionService
from src.models.pretrained.chronos_adapter import ChronosAdapter
from src.models.registry import build_default_model_registry, model_artifact_record
from src.models.sequence.fin_mamba import FinMambaBlock, FinMambaConfig
from src.models.sequence.samba_block import SambaBlock, SambaConfig


class ModelLayerTests(unittest.TestCase):
    """Baseline and adapter models should run without GPU by default."""

    def test_naive_return_baseline_predicts_without_gpu(self) -> None:
        dataset = [
            {"asset_id": 1, "symbol": "SPY", "ts": "2024-01-01", "log_return": 0.01},
            {"asset_id": 1, "symbol": "SPY", "ts": "2024-01-02", "log_return": -0.02},
        ]
        model = NaiveReturnBaseline().fit(dataset, {})

        predictions = model.predict([dataset[-1]], "1d")

        self.assertEqual(len(predictions), 1)
        self.assertEqual(predictions[0].prediction, -0.02)
        self.assertFalse(model.metadata()["requires_gpu"])

    def test_ridge_baseline_fits_small_cpu_batch(self) -> None:
        dataset = [
            {"symbol": "A", "ts": "1", "x": 1.0, "target": 2.0},
            {"symbol": "A", "ts": "2", "x": 2.0, "target": 4.0},
            {"symbol": "A", "ts": "3", "x": 3.0, "target": 6.0},
        ]
        model = RidgeReturnBaseline(alpha=0.0).fit(dataset, {"feature_columns": ["x"]})

        prediction = model.predict([{"symbol": "A", "ts": "4", "x": 4.0}], "1d")[0]

        self.assertAlmostEqual(prediction.prediction, 8.0)
        self.assertEqual(model.metadata()["feature_columns"], ["x"])

    def test_pretrained_adapter_loads_local_checkpoint(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            checkpoint = Path(temp_dir) / "chronos.json"
            checkpoint.write_text(
                json.dumps({"constant_prediction": 0.03, "confidence": 0.8}),
                encoding="utf-8",
            )
            model = ChronosAdapter.from_config({"checkpoint_path": str(checkpoint)})

            predictions = model.predict([{"symbol": "QQQ", "ts": "2024-01-01"}], 5)

            self.assertEqual(predictions[0].prediction, 0.03)
            self.assertEqual(predictions[0].confidence, 0.8)
            self.assertEqual(model.metadata()["device"], "cpu")

    def test_pretrained_adapter_without_checkpoint_fails_clearly(self) -> None:
        model = ChronosAdapter.from_config({})

        with self.assertRaisesRegex(MissingModelCheckpointError, "No local checkpoint"):
            model.predict([{"symbol": "QQQ", "ts": "2024-01-01"}], 5)

    def test_default_registry_contains_baselines_and_adapters(self) -> None:
        registry = build_default_model_registry()

        self.assertIn("naive_return", registry.names())
        self.assertIn("ridge_return", registry.names())
        self.assertIn("chronos", registry.names())
        self.assertIsInstance(registry.create("naive_return"), NaiveReturnBaseline)

    def test_sequence_placeholders_expose_required_components(self) -> None:
        fin = FinMambaBlock(FinMambaConfig(input_dim=4)).architecture_metadata()
        samba = SambaBlock(SambaConfig(input_dim=4)).architecture_metadata()

        for metadata in (fin, samba):
            components = set(metadata["components"])
            self.assertIn("state_space_sequence_block", components)
            self.assertIn("causal_convolution", components)
            self.assertIn("gated_mixing", components)
            self.assertIn("cross_asset_conditioning", components)
            self.assertIn("regime_embedding", components)
            self.assertIn("feature_projection", components)
            self.assertIn("prediction_head", components)

    def test_batch_prediction_rows_and_signal_row(self) -> None:
        prediction = NaiveReturnBaseline().fit(
            [{"asset_id": 7, "symbol": "SPY", "ts": "2024-01-01", "target": 0.02}],
            {"target_column": "target"},
        ).predict([{"asset_id": 7, "symbol": "SPY", "ts": "2024-01-02"}], "1d")[0]

        rows = prediction_rows([prediction])
        signal = signal_row(prediction)

        self.assertEqual(rows[0]["symbol"], "SPY")
        self.assertEqual(signal["asset_id"], 7)
        self.assertIsInstance(signal["ts"], datetime)
        self.assertEqual(signal["model_name"], "naive_return_baseline")
        for field in SIGNAL_EXPLANATION_FIELDS:
            self.assertIn(field, rows[0]["explanation_json"])
            self.assertIn(field, signal["explanation_json"])

    def test_online_prediction_service_keeps_bounded_buffer(self) -> None:
        model = NaiveReturnBaseline().fit(
            [{"symbol": "SPY", "ts": "1", "target": 0.01}],
            {"target_column": "target"},
        )
        service = OnlinePredictionService(model, window_size=1)

        service.update({"symbol": "SPY", "ts": "2"}, "1d")
        prediction = service.update({"symbol": "SPY", "ts": "3"}, "1d")

        self.assertEqual(service.buffer_size("SPY"), 1)
        self.assertEqual(prediction.symbol, "SPY")

    def test_model_artifact_record_matches_compatibility_schema(self) -> None:
        record = model_artifact_record(
            "chronos",
            "local-v1",
            "file:///models/chronos.json",
            {"normalizer": "identity"},
        )

        self.assertEqual(record["model_name"], "chronos")
        self.assertEqual(record["model_version"], "local-v1")
        self.assertEqual(record["metadata_json"], {"normalizer": "identity"})

    def test_sequence_metadata_exposes_phase14_xai_hooks(self) -> None:
        fin = FinMambaBlock(FinMambaConfig(input_dim=4)).architecture_metadata()
        samba = SambaBlock(SambaConfig(input_dim=4)).architecture_metadata()

        self.assertIn("latent_state_summary", fin["components"])
        for metadata in (fin, samba):
            self.assertIn("temporal_contribution_summary", metadata["components"])
            self.assertIn("feature_saliency_placeholder", metadata["components"])
