"""Phase 18 final-deliverables documentation checks."""

from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DOC_PATH = ROOT / "docs" / "final_deliverables.md"


class FinalDeliverablesDocumentationTests(unittest.TestCase):
    def test_final_deliverables_document_has_required_sections(self) -> None:
        text = DOC_PATH.read_text(encoding="utf-8")

        for heading in (
            "## 1. Summary Of Changed Files",
            "## 2. How To Run Local Mode",
            "## 3. How To Run Cloud MVP Mode",
            "## 4. How To Run The MVP Demo",
            "## 5. How To Configure Postgres",
            "## 6. How To Configure S3-Compatible Storage",
            "## 7. How To Keep SQLite Mode",
            "## 8. How To Train/Predict With Baseline",
            "## 9. How To Enable Fin-Mamba/SAMBA Models",
            "## 10. Known Limitations",
            "## 11. Next Recommended Implementation Tasks",
        ):
            self.assertIn(heading, text)

    def test_final_deliverables_include_key_commands_and_settings(self) -> None:
        text = DOC_PATH.read_text(encoding="utf-8")

        for expected in (
            "python3 -m src.cli db migrate",
            "python3 -m src.cli smoke-test",
            "CLOUD_ENV_FILE=.env.cloud make cloud-mvp-up",
            "python3 -m src.cli mvp-demo --config configs/cloud_mvp.yaml",
            "make mvp-demo",
            "DB_MODE=postgres",
            "DATABASE_URL=postgresql://",
            "STORAGE_PROVIDER=minio",
            "OBJECT_STORAGE_BUCKET=quant-lake",
            "DB_MODE=sqlite",
            "python3 -m src.cli model train --config configs/model.yaml",
            "python3 -m src.cli model predict --config configs/predict.yaml",
            "optional_sequence_models:",
            "fin_mamba_small",
            "samba_small",
        ):
            self.assertIn(expected, text)

    def test_final_deliverables_keep_research_only_boundary(self) -> None:
        text = DOC_PATH.read_text(encoding="utf-8").lower()

        self.assertIn("research, forecasting, risk, backtesting, and portfolio analytics", text)
        self.assertIn("does not claim trading profitability", text)
        self.assertIn("does not include live trading", text)
        for forbidden in (
            "guaranteed profit",
            "guaranteed profitability",
            "profitable strategy",
            "provides investment advice",
            "place orders",
            "broker connectivity enabled",
            "live trading enabled",
        ):
            self.assertNotIn(forbidden, text)

    def test_readme_links_final_deliverables(self) -> None:
        readme = (ROOT / "README.md").read_text(encoding="utf-8")

        self.assertIn("Final deliverables", readme)
        self.assertIn("docs/final_deliverables.md", readme)


if __name__ == "__main__":
    unittest.main()
