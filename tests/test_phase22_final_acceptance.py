"""Phase 22 final acceptance checks."""

from __future__ import annotations

import re
import unittest
from pathlib import Path

from src.cli import _read_config

ROOT = Path(__file__).resolve().parents[1]
CONFIG_DIR = ROOT / "configs"
DOC_PATH = ROOT / "docs" / "final_acceptance.md"


class Phase22FinalAcceptanceTests(unittest.TestCase):
    def test_final_acceptance_doc_has_17_checked_items_and_commands(self) -> None:
        text = DOC_PATH.read_text(encoding="utf-8")
        items = re.findall(r"^- \[x\] AC-(\d{2}):", text, flags=re.MULTILINE)

        self.assertEqual(items, [f"{index:02d}" for index in range(1, 18)])
        for expected in (
            "make smoke-test",
            "make pipeline-local",
            "python3 -m src.cli efficiency report --run-id",
            "make runpod-dry-run",
            "make cost-estimate",
            "docker compose -f docker-compose.local.yml config",
            "docker compose -f docker-compose.cloud.yml config",
            "python3 -m unittest discover tests",
            "python3 -m compileall src tests",
            "git diff --check",
            "No live trading",
            "RUNPOD_DRY_RUN=false",
            "RUNPOD_API_KEY",
            "--confirm-cost",
        ):
            self.assertIn(expected, text)

    def test_readme_links_final_acceptance_doc(self) -> None:
        text = (ROOT / "README.md").read_text(encoding="utf-8")

        self.assertIn("docs/final_acceptance.md", text)

    def test_local_pipeline_config_is_dependency_light_and_window_safe(self) -> None:
        config = _read_config(CONFIG_DIR / "pipeline_local_mvp.yaml")
        task_configs = config["task_configs"]
        ingest = task_configs["ingest_raw"]
        windows = task_configs["windows"]["sliding_window"]
        train_neural = task_configs["train_neural"]

        required_periods = (
            windows["train_size_days"]
            + windows["validation_size_days"]
            + windows["test_size_days"]
            + windows["horizon_days"]
            + windows["embargo_days"] * 2
        )
        self.assertLessEqual(required_periods, ingest["periods"])
        self.assertTrue(windows["purge_overlap"])
        self.assertEqual(windows["min_samples_per_window"], 1)
        self.assertFalse(train_neural["enabled"])
        self.assertEqual(config["cost_estimate"]["estimated_cost_usd"], 0.0)

    def test_runpod_configs_remain_dry_run_and_paid_submit_guarded(self) -> None:
        train_gpu = _read_config(CONFIG_DIR / "train_gpu_runpod.yaml")
        pipeline_gpu = _read_config(CONFIG_DIR / "pipeline_gpu_runpod.yaml")

        self.assertEqual(train_gpu["command"].split()[0], "python3")
        self.assertEqual(train_gpu["compute"]["provider"], "runpod")
        self.assertTrue(train_gpu["compute"]["dry_run"])
        self.assertEqual(train_gpu["max_runtime_seconds"], 3600)
        self.assertEqual(train_gpu["idle_timeout_seconds"], 300)
        self.assertTrue(train_gpu["security"]["terminate_remote_on_timeout"])
        for key in ("dataset_uri", "output_uri", "logs_uri", "metrics_uri"):
            self.assertTrue(train_gpu[key].startswith("s3://"), key)

        self.assertEqual(pipeline_gpu["compute"]["provider"], "runpod")
        self.assertTrue(pipeline_gpu["compute"]["dry_run"])
        self.assertTrue(pipeline_gpu["cost_guard"]["require_confirmation_for_paid_jobs"])
        self.assertTrue(pipeline_gpu["cost_guard"]["dry_run_default"])


if __name__ == "__main__":
    unittest.main()
