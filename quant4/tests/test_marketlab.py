"""MarketLab services under Quant4 shared models."""

from __future__ import annotations

from datetime import date

from django.test import TestCase


class MarketLabWindowTests(TestCase):
    """MarketLab windows and shuffles must stay train-only."""

    def test_no_future_leakage_in_windows(self) -> None:
        """Purged walk-forward windows keep train before validation labels."""
        from quant4.services.marketlab.windows import PurgedWalkForwardWindowBuilder

        builder = PurgedWalkForwardWindowBuilder(train_size=4, test_size=2, embargo=1)
        window = builder.build([0, 1, 2, 3, 4, 5, 6, 7], horizon=1)[0]

        self.assertLess(window.train_indices[-1] + 1, window.validation_indices[0])
        self.assertEqual(window.metadata["embargo"], 1)

    def test_shuffle_applies_only_to_train_split(self) -> None:
        """Shuffling must not mutate validation or test rows."""
        from quant4.services.marketlab.shuffling import GeneralizedTimeWindowShuffle
        from quant4.services.marketlab.windows import MarketWindow

        window = MarketWindow([0, 1, 2], [3], [4], {"index": list(range(5))})
        result = GeneralizedTimeWindowShuffle(seed=3).shuffle(
            ["a", "b", "c", "d", "e"],
            window,
        )

        self.assertCountEqual(result.train_values, ["a", "b", "c"])
        self.assertEqual(result.validation_values, ["d"])
        self.assertEqual(result.test_values, ["e"])

    def test_temporal_patch_shuffle_preserves_shape(self) -> None:
        """Patch shuffling keeps the same train-set length."""
        from quant4.services.marketlab.shuffling import TemporalPatchShuffle
        from quant4.services.marketlab.windows import MarketWindow

        window = MarketWindow([0, 1, 2, 3], [4], [5], {})
        result = TemporalPatchShuffle(patch_size=2).shuffle([1, 2, 3, 4, 5, 6], window)

        self.assertEqual(len(result.train_values), 4)
        self.assertEqual(len(result.validation_values), 1)
        self.assertEqual(len(result.test_values), 1)

    def test_overlap_shuffle_preserves_index_metadata(self) -> None:
        """Overlap shuffling carries original index metadata forward."""
        from quant4.services.marketlab.shuffling import OverlapWindowShuffle
        from quant4.services.marketlab.windows import MarketWindow

        window = MarketWindow([0, 1, 2], [3], [4], {"index": ["t0", "t1", "t2"]})
        result = OverlapWindowShuffle(overlap=1).shuffle([10, 20, 30, 40, 50], window)

        self.assertEqual(result.metadata["source_index"], ["t0", "t1", "t2"])

    def test_marketlab_window_artifacts_use_shared_quant4_model(self) -> None:
        """Window persistence uses the shared Quant4 WindowArtifact table."""
        from quant4.models import WindowArtifact
        from quant4.services.marketlab.windows import (
            MarketWindow,
            persist_window_artifact,
        )

        window = MarketWindow([0, 1], [3], [4], {"embargo": 1})

        artifact = persist_window_artifact("marketlab-window", window)

        self.assertEqual(
            WindowArtifact.objects.get(pk=artifact.pk).name,
            "marketlab-window",
        )


class MarketLabTopologyTests(TestCase):
    """Topology and decomposition fallbacks should be deterministic."""

    def test_topology_aware_shuffle_rejects_high_loss_candidate(self) -> None:
        """High topology-loss candidates are rejected before use."""
        from quant4.services.marketlab.shuffling import TopologyAwareShuffle
        from quant4.services.marketlab.windows import MarketWindow

        window = MarketWindow([0, 1, 2], [3], [4], {})
        shuffler = TopologyAwareShuffle(max_topology_loss=0.05)

        with self.assertRaisesRegex(ValueError, "topology loss"):
            shuffler.shuffle([1, 2, 3, 4, 5], window, candidate_loss=0.50)

    def test_imf_reconstruction_error_checked_when_decomposition_exists(self) -> None:
        """IMF fallback reports reconstruction error against input values."""
        from quant4.services.marketlab.decomposition import IMFDecomposer

        result = IMFDecomposer().decompose([1.0, 2.0, 3.0])

        self.assertLessEqual(result.reconstruction_error, 1e-9)
        self.assertEqual(result.method, "identity_fallback")


class MarketLabModelTests(TestCase):
    """MarketLab should persist through shared Quant4 run models."""

    def test_graph_snapshots_use_only_past_data(self) -> None:
        """Graph snapshots store an as-of-bounded data range."""
        from quant4.models import GraphSnapshot
        from quant4.services.marketlab.graph_builders import CorrelationGraphBuilder

        snapshot = CorrelationGraphBuilder().build_snapshot(
            name="past-graph",
            observations=[(date(2024, 1, 1), 1.0), (date(2024, 1, 2), 2.0)],
            as_of=date(2024, 1, 2),
        )

        stored = GraphSnapshot.objects.get(pk=snapshot.pk)
        self.assertEqual(stored.data_end, date(2024, 1, 2))
        self.assertEqual(stored.feature_schema_json["inputs"], ["date", "value"])
        self.assertEqual(stored.metrics_json["max_observation_date"], "2024-01-02")

    def test_timegan_synthetic_data_never_used_in_validation_or_test(self) -> None:
        """Synthetic rows are marked train-only."""
        from quant4.services.marketlab.datasets import build_train_only_synthetic_rows

        rows = build_train_only_synthetic_rows([[1.0, 2.0]], generator_name="timegan")

        self.assertEqual(rows[0]["split"], "train")
        self.assertFalse(rows[0]["eligible_for_validation"])
        self.assertFalse(rows[0]["eligible_for_test"])

    def test_optimizer_factory_returns_valid_optimizer(self) -> None:
        """Default optimizer factory returns local optimizer configs."""
        from quant4.services.marketlab.optimizers import OptimizerFactory

        optimizer = OptimizerFactory().create("AdamW", learning_rate=0.001)

        self.assertEqual(optimizer.name, "AdamW")
        self.assertEqual(optimizer.config["learning_rate"], 0.001)

    def test_benchmark_outputs_required_metrics(self) -> None:
        """Benchmark output is stored in shared ModelRun metrics."""
        from quant4.models import ModelRun
        from quant4.services.marketlab.evaluation import run_marketlab_benchmark

        run = run_marketlab_benchmark("bench", predictions=[1, 0], labels=[1, 1])

        stored = ModelRun.objects.get(pk=run.pk)
        self.assertEqual(stored.feature_schema_json["prediction"], "float")
        self.assertIn("accuracy", stored.metrics_json)
        self.assertIn("loss", stored.metrics_json)
        self.assertTrue(stored.metrics_json["leakage_checked"])
