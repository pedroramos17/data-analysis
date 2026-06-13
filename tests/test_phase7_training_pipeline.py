"""Tests for Phase 7 training pipeline."""

from __future__ import annotations

import json
import shutil
import tempfile
import unittest
from datetime import UTC, datetime
from pathlib import Path

from src.config.settings import load_runtime_settings
from src.pipeline.training import (
    TrainingPipelineResult,
    build_training_job_spec,
    clean_old_checkpoints,
    combined_loss,
    evaluate_all,
    mae_loss,
    mse_loss,
    run_training,
    submit_runpod_training_job,
    train_model,
    write_job_spec,
)
from src.pipeline.training.callbacks import EarlyStopping, GradientClipper, LRScheduler, MetricLogger
from src.pipeline.training.checkpointing import save_checkpoint
from src.pipeline.training.job_spec import TrainingJobSpec
from src.pipeline.training.metrics import (
    cpu_memory_mb,
    directional_accuracy,
    gpu_memory_mb,
    hit_ratio,
    information_coefficient,
    latency_per_batch_ms,
    max_drawdown,
    rank_ic,
    samples_per_second,
    sharpe_like,
    turnover_proxy,
)
from src.providers.registry import build_provider_registry


class TestLosses(unittest.TestCase):
    """Unit tests for loss functions."""

    def test_mse_loss(self) -> None:
        self.assertAlmostEqual(mse_loss([1.0, 2.0], [1.0, 2.0]), 0.0, places=6)
        self.assertAlmostEqual(mse_loss([1.0, 2.0], [2.0, 1.0]), 1.0, places=6)

    def test_mae_loss(self) -> None:
        self.assertAlmostEqual(mae_loss([1.0, 2.0], [1.0, 2.0]), 0.0, places=6)
        self.assertAlmostEqual(mae_loss([1.0, 2.0], [2.0, 1.0]), 1.0, places=6)

    def test_combined_loss(self) -> None:
        result = combined_loss([1.0, 2.0], [1.5, 2.5])
        self.assertIn("loss_total", result)
        self.assertIn("loss_mse", result)
        self.assertIn("loss_mae", result)
        self.assertGreaterEqual(result["loss_total"], 0.0)


class TestMetrics(unittest.TestCase):
    """Unit tests for evaluation metrics."""

    def test_directional_accuracy(self) -> None:
        self.assertEqual(directional_accuracy([1.0, 2.0, 3.0], [1.0, 2.0, 3.0]), 1.0)
        self.assertEqual(directional_accuracy([1.0, 2.0, 1.0], [1.0, 2.0, 3.0]), 0.5)

    def test_information_coefficient(self) -> None:
        self.assertAlmostEqual(information_coefficient([1.0, 2.0, 3.0], [1.0, 2.0, 3.0]), 1.0, places=4)
        self.assertAlmostEqual(information_coefficient([1.0, 2.0, 3.0], [3.0, 2.0, 1.0]), -1.0, places=4)

    def test_rank_ic(self) -> None:
        self.assertAlmostEqual(rank_ic([1.0, 2.0, 3.0], [1.0, 2.0, 3.0]), 1.0, places=4)

    def test_hit_ratio(self) -> None:
        self.assertEqual(hit_ratio([1.0, -1.0], [1.0, -1.0]), 1.0)
        self.assertEqual(hit_ratio([1.0, -1.0], [-1.0, 1.0]), 0.0)

    def test_sharpe_like(self) -> None:
        self.assertGreater(sharpe_like([0.01, 0.02, 0.015]), 0.0)
        self.assertEqual(sharpe_like([0.01, 0.01, 0.01]), 0.0)

    def test_max_drawdown(self) -> None:
        returns = [1.0, 1.1, 1.05, 1.2, 1.1]
        self.assertGreaterEqual(max_drawdown(returns), 0.0)
        self.assertLessEqual(max_drawdown(returns), 1.0)

    def test_turnover_proxy(self) -> None:
        self.assertEqual(turnover_proxy([1.0, 1.0, 1.0]), 0.0)
        self.assertGreater(turnover_proxy([1.0, 2.0, 1.0]), 0.0)

    def test_latency_per_batch(self) -> None:
        self.assertEqual(latency_per_batch_ms(1.0, 10), 100.0)

    def test_samples_per_second(self) -> None:
        self.assertEqual(samples_per_second(100, 1.0), 100.0)

    def test_evaluate_all(self) -> None:
        metrics = evaluate_all([1.0, 2.0, 3.0], [1.0, 2.0, 3.0])
        self.assertIn("mse", metrics)
        self.assertIn("directional_accuracy", metrics)
        self.assertIn("ic", metrics)
        self.assertIn("rank_ic", metrics)


class TestCallbacks(unittest.TestCase):
    """Unit tests for training callbacks."""

    def test_early_stopping_min_mode(self) -> None:
        es = EarlyStopping(patience=2, min_delta=0.01, mode="min")
        self.assertFalse(es(0, 1.0))
        self.assertFalse(es(1, 0.98))   # improved: 0.98 < 1.0 - 0.01
        self.assertFalse(es(2, 0.975))  # improved: 0.975 < 0.98 - 0.01
        self.assertTrue(es(3, 0.976))   # not improved 3 times
        self.assertEqual(es.stopped_epoch, 3)

    def test_early_stopping_max_mode(self) -> None:
        es = EarlyStopping(patience=2, min_delta=0.01, mode="max")
        self.assertFalse(es(0, 1.0))
        self.assertFalse(es(1, 1.02))   # improved: 1.02 > 1.0 + 0.01
        self.assertFalse(es(2, 1.03))   # improved: 1.03 > 1.02 + 0.01
        self.assertTrue(es(3, 1.029))   # not improved 3 times

    def test_gradient_clipper(self) -> None:
        gc = GradientClipper(max_norm=1.0, enabled=True)
        self.assertTrue(gc.enabled)
        # Should not raise even with a dummy model
        gc.apply(object())

    def test_lr_scheduler(self) -> None:
        sched = LRScheduler(initial_lr=0.01, decay_factor=0.5, decay_epochs=10, min_lr=1e-6)
        self.assertAlmostEqual(sched.get_lr(0), 0.01, places=6)
        self.assertAlmostEqual(sched.get_lr(10), 0.005, places=6)
        self.assertAlmostEqual(sched.get_lr(20), 0.0025, places=6)

    def test_metric_logger(self) -> None:
        logger = MetricLogger()
        logger.log(0, {"loss": 1.0}, phase="train")
        logger.log(0, {"loss": 0.9}, phase="val")
        self.assertEqual(len(logger.history), 2)
        best = logger.best_epoch("loss", "min")
        self.assertIsNotNone(best)
        self.assertEqual(best["phase"], "val")


class TestCheckpointing(unittest.TestCase):
    """Unit tests for checkpointing."""

    def setUp(self) -> None:
        self.tmpdir = tempfile.mkdtemp()

    def tearDown(self) -> None:
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_save_checkpoint_json_fallback(self) -> None:
        class DummyModel:
            pass

        record = save_checkpoint(DummyModel(), Path(self.tmpdir) / "ckpt.json", epoch=5, metric_value=0.1)
        self.assertEqual(record.epoch, 5)
        self.assertEqual(record.metric_name, "val_loss")
        self.assertTrue(Path(record.path).exists())

    def test_clean_old_checkpoints(self) -> None:
        ckpt_dir = Path(self.tmpdir) / "checkpoints"
        ckpt_dir.mkdir(parents=True, exist_ok=True)
        for i in range(5):
            (ckpt_dir / f"model_{i}.pt").write_text("dummy")
        removed = clean_old_checkpoints(ckpt_dir, keep=2)
        self.assertEqual(len(removed), 3)
        remaining = list(ckpt_dir.glob("*.pt"))
        self.assertEqual(len(remaining), 2)


class TestJobSpec(unittest.TestCase):
    """Unit tests for job spec builder."""

    def test_build_training_job_spec(self) -> None:
        config = {
            "model_name": "ridge_return",
            "dataset_uri": "data/lake/datasets/dataset=spy_rolling/window_id=0",
            "output_uri": "models/ridge",
        }
        spec = build_training_job_spec(config)
        self.assertEqual(spec.model_name, "ridge_return")
        self.assertEqual(spec.provider, "local")
        self.assertTrue(spec.command.startswith("python3 -m src.cli train run --config"))

    def test_runpod_payload(self) -> None:
        config = {
            "model_name": "fin_mamba",
            "dataset_uri": "s3://bucket/dataset",
            "output_uri": "s3://bucket/models",
        }
        spec = build_training_job_spec(config, provider="runpod")
        self.assertEqual(spec.provider, "runpod")
        payload = spec.to_runpod_payload()
        self.assertEqual(payload["name"], "train_fin_mamba")
        self.assertTrue(str(payload["command"]).startswith("python3 -m src.cli"))
        self.assertIn("payload", payload)

    def test_write_job_spec(self) -> None:
        spec = TrainingJobSpec(name="test", model_name="naive", dataset_uri="", config_path="", output_uri="", command="")
        tmpdir = tempfile.mkdtemp()
        try:
            path = write_job_spec(spec, Path(tmpdir) / "spec.json")
            self.assertTrue(path.exists())
            loaded = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(loaded["name"], "test")
        finally:
            shutil.rmtree(tmpdir, ignore_errors=True)


class TestTrainerBaselines(unittest.TestCase):
    """Integration tests for baseline model training."""

    def setUp(self) -> None:
        self.tmpdir = tempfile.mkdtemp()
        self.output_dir = Path(self.tmpdir) / "models"
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.train_rows = [
            {"symbol": "SPY", "ts": "2020-01-01T00:00:00+00:00", "close": 100.0, "open": 99.0, "target": 0.01},
            {"symbol": "SPY", "ts": "2020-01-02T00:00:00+00:00", "close": 101.0, "open": 100.0, "target": 0.01},
            {"symbol": "SPY", "ts": "2020-01-03T00:00:00+00:00", "close": 102.0, "open": 101.0, "target": 0.01},
            {"symbol": "SPY", "ts": "2020-01-04T00:00:00+00:00", "close": 103.0, "open": 102.0, "target": 0.01},
            {"symbol": "SPY", "ts": "2020-01-05T00:00:00+00:00", "close": 104.0, "open": 103.0, "target": 0.01},
        ]
        self.val_rows = [
            {"symbol": "SPY", "ts": "2020-01-06T00:00:00+00:00", "close": 105.0, "open": 104.0, "target": 0.01},
            {"symbol": "SPY", "ts": "2020-01-07T00:00:00+00:00", "close": 106.0, "open": 105.0, "target": 0.01},
        ]

    def tearDown(self) -> None:
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_train_naive_baseline(self) -> None:
        result = train_model(
            model_name="naive_return",
            train_rows=self.train_rows,
            val_rows=self.val_rows,
            config={"target_column": "target", "seed": 42},
            output_dir=self.output_dir,
        )
        self.assertEqual(result.status, "COMPLETED")
        self.assertEqual(result.model_name, "naive_return")
        self.assertGreater(len(result.train_metrics), 0)
        self.assertTrue(Path(result.model_path).exists())
        self.assertTrue(Path(result.model_card_path).exists())

    def test_train_ridge_baseline(self) -> None:
        result = train_model(
            model_name="ridge_return",
            train_rows=self.train_rows,
            val_rows=self.val_rows,
            config={"target_column": "target", "alpha": 1.0, "seed": 42},
            output_dir=self.output_dir,
        )
        self.assertEqual(result.status, "COMPLETED")
        self.assertEqual(result.model_name, "ridge_return")
        self.assertTrue(Path(result.model_path).exists())
        self.assertTrue(Path(result.model_card_path).exists())

    def test_train_with_missing_target_falls_back(self) -> None:
        rows = [
            {"symbol": "SPY", "ts": "2020-01-01T00:00:00+00:00", "close": 100.0},
            {"symbol": "SPY", "ts": "2020-01-02T00:00:00+00:00", "close": 101.0},
        ]
        result = train_model(
            model_name="naive_return",
            train_rows=rows,
            val_rows=rows,
            config={"seed": 42},
            output_dir=self.output_dir,
        )
        self.assertEqual(result.status, "COMPLETED")

    def test_model_card_generated(self) -> None:
        result = train_model(
            model_name="naive_return",
            train_rows=self.train_rows,
            val_rows=self.val_rows,
            config={"seed": 42},
            output_dir=self.output_dir,
        )
        card = json.loads(Path(result.model_card_path).read_text(encoding="utf-8"))
        self.assertIn("model_name", card)
        self.assertIn("limitations", card)
        self.assertIn("train_metrics", card)


class TestTrainerNeural(unittest.TestCase):
    """Integration tests for neural model training (CPU-safe)."""

    def setUp(self) -> None:
        self.tmpdir = tempfile.mkdtemp()
        self.output_dir = Path(self.tmpdir) / "models"
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.train_rows = [
            {"symbol": "SPY", "ts": "2020-01-01T00:00:00+00:00", "f0": 1.0, "f1": 2.0, "target": 0.5},
            {"symbol": "SPY", "ts": "2020-01-02T00:00:00+00:00", "f0": 1.1, "f1": 2.1, "target": 0.6},
            {"symbol": "SPY", "ts": "2020-01-03T00:00:00+00:00", "f0": 1.2, "f1": 2.2, "target": 0.7},
            {"symbol": "SPY", "ts": "2020-01-04T00:00:00+00:00", "f0": 1.3, "f1": 2.3, "target": 0.8},
            {"symbol": "SPY", "ts": "2020-01-05T00:00:00+00:00", "f0": 1.4, "f1": 2.4, "target": 0.9},
        ]
        self.val_rows = [
            {"symbol": "SPY", "ts": "2020-01-06T00:00:00+00:00", "f0": 1.5, "f1": 2.5, "target": 1.0},
            {"symbol": "SPY", "ts": "2020-01-07T00:00:00+00:00", "f0": 1.6, "f1": 2.6, "target": 1.1},
        ]

    def tearDown(self) -> None:
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_train_tcn_cpu(self) -> None:
        result = train_model(
            model_name="tcn",
            train_rows=self.train_rows,
            val_rows=self.val_rows,
            config={"input_dim": 2, "hidden_dim": 8, "epochs": 1, "seed": 42, "device": "cpu"},
            output_dir=self.output_dir,
        )
        # Falls back to baseline if torch not installed
        self.assertIn(result.status, {"COMPLETED", "COMPLETED_FALLBACK"})
        self.assertTrue(Path(result.model_path).exists())

    def test_train_samba_cpu(self) -> None:
        result = train_model(
            model_name="samba",
            train_rows=self.train_rows,
            val_rows=self.val_rows,
            config={"input_dim": 2, "hidden_dim": 8, "epochs": 1, "seed": 42, "device": "cpu"},
            output_dir=self.output_dir,
        )
        self.assertIn(result.status, {"COMPLETED", "COMPLETED_FALLBACK"})
        self.assertTrue(Path(result.model_path).exists())

    def test_train_fin_mamba_cpu(self) -> None:
        result = train_model(
            model_name="fin_mamba",
            train_rows=self.train_rows,
            val_rows=self.val_rows,
            config={"input_dim": 2, "hidden_dim": 8, "epochs": 1, "seed": 42, "device": "cpu"},
            output_dir=self.output_dir,
        )
        self.assertIn(result.status, {"COMPLETED", "COMPLETED_FALLBACK"})
        self.assertTrue(Path(result.model_path).exists())


class TestTrainingPipeline(unittest.TestCase):
    """Integration tests for the full training pipeline runner."""

    def setUp(self) -> None:
        self.tmpdir = tempfile.mkdtemp()
        self.lake_root = Path(self.tmpdir) / "lake"
        self.lake_root.mkdir(parents=True, exist_ok=True)
        self.output_root = self.lake_root / "models"
        # Write mock dataset
        from src.pipeline.ingestion.validators import rows_to_parquet_bytes
        train_rows = [
            {"symbol": "SPY", "ts": "2020-01-01T00:00:00+00:00", "close": 100.0, "target": 0.01},
            {"symbol": "SPY", "ts": "2020-01-02T00:00:00+00:00", "close": 101.0, "target": 0.01},
            {"symbol": "SPY", "ts": "2020-01-03T00:00:00+00:00", "close": 102.0, "target": 0.01},
        ]
        val_rows = [
            {"symbol": "SPY", "ts": "2020-01-04T00:00:00+00:00", "close": 103.0, "target": 0.01},
            {"symbol": "SPY", "ts": "2020-01-05T00:00:00+00:00", "close": 104.0, "target": 0.01},
        ]
        dataset_dir = self.lake_root / "datasets" / "dataset=test" / "version=v1" / "window_id=0"
        dataset_dir.mkdir(parents=True, exist_ok=True)
        (dataset_dir / "train.parquet").write_bytes(rows_to_parquet_bytes(train_rows))
        (dataset_dir / "validation.parquet").write_bytes(rows_to_parquet_bytes(val_rows))
        self.registry = build_provider_registry(load_runtime_settings())

    def tearDown(self) -> None:
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_run_training_single(self) -> None:
        config = {
            "model_name": "naive_return",
            "dataset_path": str(self.lake_root / "datasets" / "dataset=test" / "version=v1" / "window_id=0"),
            "output_root": str(self.output_root),
            "target_column": "target",
            "epochs": 1,
            "seed": 42,
            "require_duckdb": False,
        }
        result = run_training(config, self.registry)
        self.assertEqual(result.status, "COMPLETED")
        self.assertEqual(result.model_name, "naive_return")
        self.assertEqual(len(result.outputs), 1)
        self.assertTrue(Path(result.outputs[0].model_path).exists())

    def test_run_training_windowed(self) -> None:
        config = {
            "model_name": "naive_return",
            "dataset_name": "test",
            "version": "v1",
            "training_mode": "windowed",
            "dataset_path": str(self.lake_root / "datasets"),
            "output_root": str(self.output_root),
            "target_column": "target",
            "epochs": 1,
            "seed": 42,
            "require_duckdb": False,
        }
        result = run_training(config, self.registry)
        self.assertEqual(result.status, "COMPLETED")
        self.assertGreaterEqual(len(result.outputs), 1)

    def test_runpod_spec_generation(self) -> None:
        # Create a minimal dataset so single training doesn't fail before spec gen
        dataset_dir = self.lake_root / "datasets" / "dataset=spy" / "version=v1" / "window_id=0"
        dataset_dir.mkdir(parents=True, exist_ok=True)
        from src.pipeline.ingestion.validators import rows_to_parquet_bytes
        rows = [{"symbol": "SPY", "ts": "2020-01-01T00:00:00+00:00", "close": 100.0, "target": 0.01}]
        (dataset_dir / "train.parquet").write_bytes(rows_to_parquet_bytes(rows))
        (dataset_dir / "validation.parquet").write_bytes(rows_to_parquet_bytes(rows))
        config = {
            "model_name": "ridge_return",
            "dataset_path": str(dataset_dir),
            "output_root": str(self.output_root),
            "generate_runpod_spec": True,
            "target_column": "target",
            "epochs": 1,
            "seed": 42,
            "require_duckdb": False,
        }
        result = run_training(config, self.registry)
        self.assertEqual(result.status, "COMPLETED")
        self.assertIsNotNone(result.runpod_spec_path)
        self.assertTrue(Path(result.runpod_spec_path).exists())
        spec = json.loads(Path(result.runpod_spec_path).read_text(encoding="utf-8"))
        self.assertEqual(spec["provider"], "runpod")

    def test_submit_runpod_training_job_dry_run(self) -> None:
        config = {
            "model_name": "fin_mamba",
            "dataset_uri": "s3://bucket/dataset",
            "output_uri": "s3://bucket/models",
        }
        result = submit_runpod_training_job(config, self.registry)
        self.assertEqual(result["status"], "PLANNED")
        self.assertIn("job_id", result)


if __name__ == "__main__":
    unittest.main()
