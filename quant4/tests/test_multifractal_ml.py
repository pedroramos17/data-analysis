"""Quant4 multifractal Phase 12 ML integration tests."""

from __future__ import annotations

import builtins
from unittest.mock import patch

from django.test import SimpleTestCase


class Quant4MultifractalMLTests(SimpleTestCase):
    """ML helpers should build time-safe datasets and honest evaluations."""

    def test_supervised_dataset_uses_horizon_targets(self) -> None:
        """Feature rows at t map to targets at t + horizon."""
        from quant4.services.multifractal.ml.datasets import build_supervised_dataset

        rows = build_supervised_dataset(_features(6), [0.0, 0.1, -0.2, 0.3, 0.4, -0.5])

        self.assertEqual(rows[0].source_index, 0)
        self.assertEqual(rows[0].target_index, 1)
        self.assertEqual(rows[0].targets["next_return_sign"], 1.0)

    def test_walk_forward_split_has_purge_gap(self) -> None:
        """Walk-forward splits keep train and test ranges ordered."""
        from quant4.services.multifractal.ml.datasets import build_walk_forward_splits

        splits = build_walk_forward_splits(24, train_size=8, test_size=4, purge_gap=2)

        self.assertLess(splits[0].train_indices[-1], splits[0].test_indices[0])
        self.assertEqual(splits[0].test_indices[0] - splits[0].train_indices[-1], 3)

    def test_majority_baseline_runs_without_optional_dependencies(self) -> None:
        """Fallback classifier emits deterministic local predictions."""
        from quant4.services.multifractal.ml.baselines import fit_baseline_classifier
        from quant4.services.multifractal.ml.datasets import build_supervised_dataset

        dataset = build_supervised_dataset(_features(8), [0.0, 0.1, 0.2, -0.1] * 2)
        report = fit_baseline_classifier(
            dataset[:4],
            dataset[4:],
            "next_return_sign",
            model_name="majority",
        )

        self.assertEqual(len(report.predictions), len(dataset[4:]))
        self.assertEqual(report.metadata["dependency"], "local_fallback")

    def test_optional_sklearn_model_fails_clearly_when_missing(self) -> None:
        """Optional sklearn models must not silently become majority fallback."""
        from quant4.services.multifractal.ml.baselines import fit_baseline_classifier
        from quant4.services.multifractal.ml.datasets import build_supervised_dataset

        dataset = build_supervised_dataset(_features(8), [0.0, 0.1, 0.2, -0.1] * 2)

        missing_dependency = "logistic_regression.*scikit-learn"
        with patch.object(builtins, "__import__", side_effect=_missing_sklearn_import):
            with self.assertRaisesRegex(RuntimeError, missing_dependency):
                fit_baseline_classifier(
                    dataset[:4],
                    dataset[4:],
                    "next_return_sign",
                    model_name="logistic_regression",
                )

    def test_invalid_baseline_model_name_fails_clearly(self) -> None:
        """Unsupported model names enumerate the accepted local baselines."""
        from quant4.services.multifractal.ml.baselines import fit_baseline_classifier
        from quant4.services.multifractal.ml.datasets import build_supervised_dataset

        dataset = build_supervised_dataset(_features(8), [0.0, 0.1, 0.2, -0.1] * 2)

        with self.assertRaisesRegex(ValueError, "unknown_model.*majority"):
            fit_baseline_classifier(
                dataset[:4],
                dataset[4:],
                "next_return_sign",
                model_name="unknown_model",
            )

    def test_walk_forward_evaluation_does_not_claim_performance(self) -> None:
        """Evaluation metrics are reported without predictive claims."""
        from quant4.services.multifractal.ml.datasets import build_supervised_dataset
        from quant4.services.multifractal.ml.evaluation import evaluate_walk_forward

        returns = [0.02, -0.01, 0.03, -0.02] * 5
        dataset = build_supervised_dataset(_features(20), returns)
        result = evaluate_walk_forward(dataset, "next_return_sign", 8, 4)

        self.assertFalse(result["claims_predictive_performance"])
        self.assertEqual(result["validation_method"], "walk_forward")
        self.assertIn("aggregate", result)


def _features(length: int) -> list[dict[str, float]]:
    return [
        {
            "close": 100.0 + index,
            "volume": 1000.0 + index,
            "hurst_h2": 0.5,
            "delta_alpha": 0.2,
            "risk_score": 0.1,
        }
        for index in range(length)
    ]


def _missing_sklearn_import(
    name: str,
    globals_: object | None = None,
    locals_: object | None = None,
    fromlist: tuple[str, ...] = (),
    level: int = 0,
) -> object:
    if name.startswith("sklearn"):
        raise ImportError("missing sklearn")
    return _ORIGINAL_IMPORT(name, globals_, locals_, fromlist, level)


_ORIGINAL_IMPORT = builtins.__import__
