"""Phase 0 architecture contract tests."""

from __future__ import annotations

import importlib
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]

ARCHITECTURE_DOCS = (
    "docs/architecture/current_state.md",
    "docs/architecture/target_state.md",
    "docs/architecture/migration_plan.md",
    "docs/architecture/module_contracts.md",
)

SOURCEFLOW_BOUNDARIES = (
    "sourceflow.ingestion",
    "sourceflow.normalization",
    "sourceflow.entities",
    "sourceflow.claims",
    "sourceflow.events",
    "sourceflow.kg",
    "sourceflow.reasoning",
    "sourceflow.tms",
    "sourceflow.retrieval",
    "sourceflow.graphrag",
    "sourceflow.quant",
    "sourceflow.evaluation",
    "sourceflow.api",
)


class Phase0ArchitectureContractTests(unittest.TestCase):
    def test_phase0_architecture_documents_exist(self) -> None:
        for relative_path in ARCHITECTURE_DOCS:
            with self.subTest(path=relative_path):
                self.assertTrue((ROOT / relative_path).is_file())

    def test_sourceflow_boundaries_import(self) -> None:
        for module_name in SOURCEFLOW_BOUNDARIES:
            with self.subTest(module=module_name):
                module = importlib.import_module(module_name)

                self.assertEqual(module.__name__, module_name)


if __name__ == "__main__":
    unittest.main()
