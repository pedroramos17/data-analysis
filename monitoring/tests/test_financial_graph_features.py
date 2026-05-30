"""Tests for finance graph feature extraction."""

from __future__ import annotations

from django.test import SimpleTestCase


class FinancialGraphFeatureTests(SimpleTestCase):
    """Finance graph features combine relations and corrected correlations."""

    def test_relation_exposure_and_degree_features(self) -> None:
        """Weighted relation edges propagate exposure scores."""
        from sourceflow.finance_graph.graph_builder import build_financial_graph
        from sourceflow.finance_graph.graph_features import graph_feature_rows

        graph = build_financial_graph(
            instruments=["BANK", "BORROWER"],
            relations=[
                {
                    "source": "BANK",
                    "target": "BORROWER",
                    "relation_type": "lender_borrower",
                    "weight": 0.5,
                }
            ],
        )
        rows = graph_feature_rows(graph, {"BANK": 1.0})

        borrower = rows["BORROWER"]
        self.assertEqual(borrower["in_degree"], 1)
        self.assertGreater(borrower["rates_exposure"], 0.0)

    def test_fundamental_similarity_uses_available_metrics(self) -> None:
        """Comparable valuation/profitability fields produce a similarity edge."""
        from sourceflow.finance_graph.fundamental_features import (
            fundamental_similarity,
        )

        score = fundamental_similarity(
            {"gross_margin": 0.4, "debt_to_equity": 1.0},
            {"gross_margin": 0.42, "debt_to_equity": 1.1},
        )

        self.assertGreater(score, 0.8)
