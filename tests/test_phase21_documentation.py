"""Phase 21 documentation coverage checks."""

from __future__ import annotations

import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

REQUIRED_DOCS = (
    "docs/pipeline/ingestion.md",
    "docs/pipeline/preprocessing.md",
    "docs/pipeline/features.md",
    "docs/pipeline/sliding_windows.md",
    "docs/pipeline/training.md",
    "docs/pipeline/evaluation.md",
    "docs/cloud/runpod_secure_hourly.md",
    "docs/cloud/autoscaling.md",
    "docs/security/rate_limits.md",
    "docs/cost/cost_minimization.md",
    "docs/observability/code_efficiency.md",
    "docs/runbooks/local_mvp.md",
    "docs/runbooks/gpu_training_runpod.md",
)


class Phase21DocumentationTests(unittest.TestCase):
    def test_required_docs_exist_and_link_commands(self) -> None:
        for relative in REQUIRED_DOCS:
            with self.subTest(relative=relative):
                path = ROOT / relative
                self.assertTrue(path.exists(), f"missing {relative}")
                text = path.read_text(encoding="utf-8")
                self.assertIn("# ", text)
                self.assertIn("python3 -m src.cli", text)

    def test_readme_has_requested_mermaid_diagrams(self) -> None:
        text = (ROOT / "README.md").read_text(encoding="utf-8")

        self.assertIn("ingest[ingest] --> preprocess[preprocess]", text)
        self.assertIn("preprocess --> features[features]", text)
        self.assertIn("features --> sliding_windows[sliding windows]", text)
        self.assertIn("sliding_windows --> train[train]", text)
        self.assertIn("train --> predict[predict]", text)
        self.assertIn("predict --> evaluate[evaluate]", text)
        self.assertIn("evaluate --> backtest[backtest]", text)
        self.assertIn("backtest --> risk[risk]", text)
        self.assertIn("risk --> report[report]", text)
        self.assertIn("local_orchestrator[local orchestrator] --> queue[queue]", text)
        self.assertIn("queue --> autoscaler[autoscaler]", text)
        self.assertIn("autoscaler --> runpod_pod[RunPod pod]", text)
        self.assertIn("runpod_pod --> object_storage[object storage]", text)
        self.assertIn("object_storage --> model_registry[model registry]", text)
        self.assertIn("model_registry --> evaluation_report[evaluation report]", text)

    def test_readme_covers_phase21_operational_topics(self) -> None:
        text = (ROOT / "README.md").read_text(encoding="utf-8")

        for expected in (
            "Local MVP",
            "RunPod Dry Run",
            "Real RunPod Submit",
            "Cost Guard",
            "Rate Limits",
            "Efficiency Reports",
            "SQLite And Cloud Mode",
            "docs/cloud/runpod_secure_hourly.md",
            "docs/cost/cost_minimization.md",
            "docs/security/rate_limits.md",
            "docs/observability/code_efficiency.md",
            "docs/runbooks/local_mvp.md",
            "docs/runbooks/gpu_training_runpod.md",
        ):
            self.assertIn(expected, text)

    def test_runpod_docs_keep_paid_submit_guarded(self) -> None:
        text = (ROOT / "docs" / "cloud" / "runpod_secure_hourly.md").read_text(encoding="utf-8")

        self.assertIn("RUNPOD_DRY_RUN=false", text)
        self.assertIn("RUNPOD_API_KEY", text)
        self.assertIn("--confirm-cost", text)
        self.assertIn("launches_paid_infrastructure=false", text)
        self.assertIn("No secrets are copied into the image", text)


if __name__ == "__main__":
    unittest.main()
