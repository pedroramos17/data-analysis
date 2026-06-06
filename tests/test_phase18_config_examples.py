"""Phase 18 config example checks."""

from __future__ import annotations

import unittest
from pathlib import Path

from src.cli import _read_config

ROOT = Path(__file__).resolve().parents[1]
CONFIG_DIR = ROOT / "configs"

REQUIRED_CONFIGS = (
    "ingest_sample.yaml",
    "preprocess_mvp.yaml",
    "features_mvp.yaml",
    "sliding_window_mvp.yaml",
    "train_baseline.yaml",
    "train_fin_mamba_small.yaml",
    "train_samba_small.yaml",
    "train_gpu_runpod.yaml",
    "evaluate_mvp.yaml",
    "backtest_mvp.yaml",
    "pipeline_local_mvp.yaml",
    "pipeline_gpu_runpod.yaml",
    "cost_limits.yaml",
    "rate_limits.yaml",
)


class Phase18ConfigExampleTests(unittest.TestCase):
    def test_required_config_examples_exist_and_parse(self) -> None:
        for filename in REQUIRED_CONFIGS:
            with self.subTest(filename=filename):
                path = CONFIG_DIR / filename
                self.assertTrue(path.exists(), f"missing {filename}")
                self.assertIsInstance(_read_config(path), dict)

    def test_sliding_window_example_has_required_policy(self) -> None:
        config = _read_config(CONFIG_DIR / "sliding_window_mvp.yaml")
        window = config["sliding_window"]

        self.assertEqual(window["mode"], "rolling")
        self.assertEqual(window["train_size_days"], 730)
        self.assertEqual(window["validation_size_days"], 90)
        self.assertEqual(window["test_size_days"], 90)
        self.assertEqual(window["step_size_days"], 30)
        self.assertEqual(window["embargo_days"], 5)
        self.assertEqual(window["horizon_days"], 5)
        self.assertTrue(window["purge_overlap"])

    def test_cost_example_is_dry_run_and_confirmation_first(self) -> None:
        config = _read_config(CONFIG_DIR / "cost_limits.yaml")
        guard = config["cost_guard"]

        self.assertEqual(guard["max_cost_per_job_usd"], 2.0)
        self.assertEqual(guard["max_daily_cost_usd"], 5.0)
        self.assertTrue(guard["require_confirmation_for_paid_jobs"])
        self.assertTrue(guard["dry_run_default"])

    def test_runpod_examples_are_dry_run_by_default(self) -> None:
        for filename in ("train_gpu_runpod.yaml", "pipeline_gpu_runpod.yaml"):
            with self.subTest(filename=filename):
                config = _read_config(CONFIG_DIR / filename)
                compute = config["compute"]

                self.assertEqual(compute["provider"], "runpod")
                self.assertTrue(compute["dry_run"])
                self.assertEqual(compute["max_job_minutes"], 60)
                self.assertEqual(compute["idle_timeout_seconds"], 300)
                self.assertLessEqual(compute["max_hourly_cost_usd"], 0.5)
                self.assertTrue(compute["prefer_spot"])


if __name__ == "__main__":
    unittest.main()
