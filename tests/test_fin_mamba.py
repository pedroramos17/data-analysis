"""Tests for the budget-friendly Fin-Mamba architecture module."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from src.models.base import MissingModelDependencyError
from src.models.sequence._torch import torch_modules
from src.models.sequence.fin_mamba import FinMambaBlock, FinMambaConfig


class FinMambaArchitectureTests(unittest.TestCase):
    """Fin-Mamba should support CPU inference and stable checkpoints."""

    def test_forward_shapes_with_optional_context(self) -> None:
        """All configured heads and diagnostics should have stable shapes."""
        torch = _torch_or_skip(self)
        config = FinMambaConfig(
            input_dim=5,
            hidden_dim=8,
            num_layers=2,
            dropout=0.0,
            horizon=3,
            regime_classes=4,
        )
        model = FinMambaBlock(config).build()
        x_time = torch.randn(2, 7, 5)
        x_cross = torch.randn(2, 4, 3)
        regime_features = torch.randn(2, 7, 2)
        graph_features = torch.randn(2, 4, 6)

        output = model(
            x_time,
            x_cross=x_cross,
            regime_features=regime_features,
            graph_features=graph_features,
            return_diagnostics=True,
        )

        predictions = output["predictions"]
        self.assertEqual(predictions["return_forecast"].shape, (2, 3))
        self.assertEqual(predictions["volatility_forecast"].shape, (2, 3))
        self.assertEqual(predictions["drawdown_risk"].shape, (2, 3))
        self.assertEqual(predictions["regime_probability"].shape, (2, 3, 4))
        self.assertEqual(predictions["signal_confidence"].shape, (2, 3))
        self.assertEqual(output["latent_states"]["sequence"].shape, (2, 7, 8))
        self.assertEqual(output["latent_states"]["pooled"].shape, (2, 8))
        self.assertEqual(output["diagnostics"]["cross_asset_weights"].shape, (2, 8))
        torch.testing.assert_close(
            output["diagnostics"]["cross_asset_weights"].sum(dim=1),
            torch.ones(2),
        )

    def test_cpu_forward_pass_without_optional_context(self) -> None:
        """The base model path should run on CPU with only time-series inputs."""
        torch = _torch_or_skip(self)
        config = FinMambaConfig(
            input_dim=3,
            hidden_dim=6,
            num_layers=1,
            dropout=0.0,
            horizon=2,
            asset_conditioning=False,
            use_regime_features=False,
            use_graph_features=False,
            output_targets=("return_forecast", "signal_confidence"),
        )
        model = FinMambaBlock(config).build()
        x_time = torch.randn(4, 5, 3)

        output = model(x_time)

        self.assertEqual(set(output["predictions"]), {"return_forecast", "signal_confidence"})
        self.assertEqual(output["predictions"]["return_forecast"].device.type, "cpu")
        self.assertEqual(output["predictions"]["signal_confidence"].shape, (4, 2))

    def test_save_and_load_checkpoint_round_trips_predictions(self) -> None:
        """A saved checkpoint should restore matching CPU predictions."""
        torch = _torch_or_skip(self)
        torch.manual_seed(2026)
        config = FinMambaConfig(input_dim=4, hidden_dim=8, dropout=0.0, horizon=2)
        model = FinMambaBlock(config).build()
        model.eval()
        x_time = torch.randn(2, 6, 4)
        x_cross = torch.randn(2, 3, 5)
        regime_features = torch.randn(2, 6, 2)
        graph_features = torch.randn(2, 3, 4)
        expected = model(
            x_time,
            x_cross=x_cross,
            regime_features=regime_features,
            graph_features=graph_features,
        )["predictions"]

        with tempfile.TemporaryDirectory() as temp_dir:
            checkpoint = Path(temp_dir) / "fin_mamba.pt"
            model.save_checkpoint(checkpoint)
            restored = FinMambaBlock(config).build()
            restored.eval()
            restored(
                x_time,
                x_cross=x_cross,
                regime_features=regime_features,
                graph_features=graph_features,
            )
            restored.load_checkpoint(checkpoint)
            actual = restored(
                x_time,
                x_cross=x_cross,
                regime_features=regime_features,
                graph_features=graph_features,
            )["predictions"]

        for target in expected:
            torch.testing.assert_close(actual[target], expected[target])

    def test_deterministic_seed_smoke(self) -> None:
        """Identical seeds and inputs should produce identical initial outputs."""
        torch = _torch_or_skip(self)
        x_time = torch.randn(2, 5, 3)
        config = FinMambaConfig(
            input_dim=3,
            hidden_dim=6,
            num_layers=1,
            dropout=0.0,
            horizon=1,
            asset_conditioning=False,
            use_regime_features=False,
            use_graph_features=False,
        )

        torch.manual_seed(123)
        left = FinMambaBlock(config).build()(x_time)["predictions"]
        torch.manual_seed(123)
        right = FinMambaBlock(config).build()(x_time)["predictions"]

        for target in left:
            torch.testing.assert_close(left[target], right[target])


def _torch_or_skip(testcase: unittest.TestCase) -> object:
    try:
        torch, _nn = torch_modules("Fin-Mamba tests")
    except MissingModelDependencyError as exc:
        testcase.skipTest(str(exc))
    return torch


if __name__ == "__main__":
    unittest.main()
