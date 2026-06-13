"""Tests for the SAMBA financial sequence architecture module."""

from __future__ import annotations

import unittest
from pathlib import Path

from src.models.base import MissingModelDependencyError
from src.models.registry import build_default_model_registry
from src.models.sequence._torch import torch_modules
from src.models.sequence.samba_block import (
    SambaBlock,
    SambaConfig,
    SambaEncoder,
    SambaForecastModel,
)


class SambaArchitectureTests(unittest.TestCase):
    """SAMBA should be registry-friendly and CPU-safe."""

    def test_architecture_metadata_exposes_required_components(self) -> None:
        """Metadata should describe the hybrid branches without importing Torch."""
        metadata = SambaBlock(SambaConfig(input_dim=4)).architecture_metadata()
        components = set(metadata["components"])

        self.assertEqual(metadata["architecture"], "samba")
        self.assertIn("local_causal_convolution_branch", components)
        self.assertIn("state_space_sequence_block", components)
        self.assertIn("low_rank_attention_branch", components)
        self.assertIn("gated_fusion", components)
        self.assertIn("residual_normalization", components)
        self.assertIn("branch_contribution_weights", components)
        self.assertIn("feature_saliency_placeholder", components)
        self.assertIn("temporal_contribution_summary", components)

    def test_default_registry_creates_samba_forecast_model(self) -> None:
        """SAMBA should be available as a drop-in forecast model factory."""
        registry = build_default_model_registry()

        model = registry.create("samba", {"input_dim": 3, "hidden_dim": 8})

        self.assertIsInstance(model, SambaForecastModel)
        self.assertIn("samba", registry.names())
        self.assertEqual(model.metadata()["architecture"], "samba")
        self.assertFalse(model.metadata()["requires_gpu"])

    def test_yaml_config_example_exists(self) -> None:
        """The SAMBA YAML example should document config and output contracts."""
        config_path = Path("configs/samba.yaml")

        text = config_path.read_text(encoding="utf-8")

        self.assertIn("name: samba", text)
        self.assertIn("input_dim:", text)
        self.assertIn("attention_rank:", text)
        self.assertIn("branch_contribution_weights", text)
        self.assertIn("uncertainty_proxy", text)

    def test_block_forward_shapes_and_diagnostics(self) -> None:
        """One SAMBA block should return encoded states and branch diagnostics."""
        torch = _torch_or_skip(self)
        config = SambaConfig(input_dim=5, hidden_dim=8, attention_rank=4, dropout=0.0)
        block = SambaBlock(config).build()
        hidden = torch.randn(2, 7, 8)

        output = block(hidden, return_diagnostics=True)

        diagnostics = output["diagnostics"]
        self.assertEqual(output["encoded"].shape, (2, 7, 8))
        self.assertEqual(diagnostics["branch_contribution_weights"].shape, (2, 7, 3))
        self.assertEqual(diagnostics["branch_contribution_summary"].shape, (2, 3))
        self.assertEqual(diagnostics["feature_saliency_placeholder"].shape, (2, 8))
        self.assertEqual(diagnostics["temporal_contribution_summary"].shape, (2, 7))
        torch.testing.assert_close(
            diagnostics["branch_contribution_weights"].sum(dim=-1),
            torch.ones(2, 7),
        )

    def test_encoder_forward_with_cross_asset_context(self) -> None:
        """The encoder should combine sequence and cross-asset context on CPU."""
        torch = _torch_or_skip(self)
        config = SambaConfig(
            input_dim=5,
            hidden_dim=8,
            num_layers=2,
            attention_rank=4,
            attention_stride=2,
            dropout=0.0,
        )
        encoder = SambaEncoder(config).build()
        x_time = torch.randn(2, 9, 5)
        x_cross = torch.randn(2, 4, 6)

        output = encoder(x_time, x_cross=x_cross, return_diagnostics=True)

        diagnostics = output["diagnostics"]
        self.assertEqual(output["encoded"].shape, (2, 9, 8))
        self.assertEqual(output["pooled"].shape, (2, 8))
        self.assertEqual(diagnostics["cross_asset_weights"].shape, (2, 4))
        self.assertEqual(diagnostics["branch_contribution_weights"].shape, (2, 2, 9, 3))
        self.assertEqual(diagnostics["branch_contribution_summary"].shape, (2, 3))
        self.assertEqual(diagnostics["feature_saliency_placeholder"].shape, (2, 5))

    def test_forecast_model_forward_outputs_contract(self) -> None:
        """The forecast module should return forecast, uncertainty, and diagnostics."""
        torch = _torch_or_skip(self)
        config = SambaConfig(
            input_dim=4,
            hidden_dim=8,
            num_layers=1,
            horizon=3,
            output_dim=1,
            attention_rank=4,
            dropout=0.0,
        )
        module = SambaForecastModel(config).build()
        x_time = torch.randn(2, 6, 4)
        x_cross = torch.randn(2, 3, 5)

        output = module(x_time, x_cross=x_cross, return_diagnostics=True)

        self.assertEqual(output["forecast"].shape, (2, 3, 1))
        self.assertEqual(output["uncertainty_proxy"].shape, (2, 3, 1))
        self.assertEqual(output["latent_states"]["sequence"].shape, (2, 6, 8))
        self.assertIn("branch_contribution_summary", output["branch_diagnostics"])

    def test_row_based_predict_uses_registry_wrapper(self) -> None:
        """The BaseForecastModel wrapper should emit forecast prediction rows."""
        _torch_or_skip(self)
        model = SambaForecastModel.from_config(
            {
                "input_dim": 2,
                "hidden_dim": 8,
                "num_layers": 1,
                "horizon": 1,
                "attention_rank": 4,
                "feature_columns": ["x1", "x2"],
            }
        )
        dataset = [
            {"symbol": "SPY", "ts": "2024-01-01", "x1": 0.1, "x2": 0.2},
            {"symbol": "QQQ", "ts": "2024-01-01", "x1": -0.1, "x2": 0.4},
        ]

        predictions = model.predict(dataset, "1d")

        self.assertEqual(len(predictions), 2)
        self.assertEqual(predictions[0].model_name, "samba_forecast")
        self.assertEqual(predictions[0].horizon, "1d")
        self.assertIsInstance(predictions[0].prediction, float)


def _torch_or_skip(testcase: unittest.TestCase) -> object:
    try:
        torch, _nn = torch_modules("SAMBA tests")
    except MissingModelDependencyError as exc:
        testcase.skipTest(str(exc))
    return torch


if __name__ == "__main__":
    unittest.main()
