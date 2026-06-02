"""Tests for the QuantSpace to Sourceflow symbolic formula adapter."""

from __future__ import annotations

from django.test import TestCase

from quantspace.models import FactorCandidate, Paper


class SourceflowAdapterTests(TestCase):
    """The adapter must be validity-neutral and persistence-free."""

    def test_simple_unary_formula_adapts(self) -> None:
        """A supported unary expression becomes Sourceflow formula JSON."""
        from quantspace.services.sourceflow_adapter import (
            adapt_factor_candidate_to_sourceflow_formula,
            can_adapt_factor_candidate,
        )

        candidate = _candidate(
            {
                "kind": "unary",
                "operator": "zscore",
                "input": {"kind": "operand", "name": "returns"},
            }
        )

        self.assertTrue(can_adapt_factor_candidate(candidate))
        formula = adapt_factor_candidate_to_sourceflow_formula(candidate)

        self.assertEqual(formula["expression_json"]["name"], "zscore")
        self.assertEqual(formula["expression_json"]["input"]["name"], "returns")
        self.assertEqual(formula["metadata"]["validation_status"], "NEEDS_BACKTEST")

    def test_binary_div_safe_formula_adapts(self) -> None:
        """The documented div_safe binary shape is preserved."""
        from quantspace.services.sourceflow_adapter import (
            adapt_factor_candidate_to_sourceflow_formula,
        )

        candidate = _candidate(
            {
                "kind": "binary",
                "name": "div_safe",
                "left": {"kind": "operand", "name": "article_count"},
                "right": {"kind": "constant", "value": 1.0},
            }
        )

        formula = adapt_factor_candidate_to_sourceflow_formula(candidate)

        self.assertEqual(formula["expression_json"]["kind"], "binary")
        self.assertEqual(formula["expression_json"]["name"], "div_safe")
        self.assertEqual(formula["expression_json"]["right"]["value"], 1.0)

    def test_unsupported_operator_returns_clear_limitation(self) -> None:
        """Unsupported operators are reported instead of adapted."""
        from quantspace.services.sourceflow_adapter import (
            can_adapt_factor_candidate,
            explain_adapter_limitations,
        )

        candidate = _candidate(
            {
                "kind": "unary",
                "operator": "causal_discovery",
                "input": {"kind": "operand", "name": "returns"},
            }
        )

        self.assertFalse(can_adapt_factor_candidate(candidate))
        self.assertIn(
            "Unsupported operator 'causal_discovery'",
            limitations_text(candidate),
        )
        self.assertIn("rank", " ".join(explain_adapter_limitations(candidate)))

    def test_missing_unary_input_returns_limitation(self) -> None:
        """Incomplete formula nodes are rejected at the adapter boundary."""
        from quantspace.services.sourceflow_adapter import (
            can_adapt_factor_candidate,
        )

        candidate = _candidate({"kind": "unary", "operator": "rank"})

        self.assertFalse(can_adapt_factor_candidate(candidate))
        self.assertIn(
            "expression_json.input is missing",
            limitations_text(candidate),
        )

    def test_supported_initial_operators_are_accepted(self) -> None:
        """Every initial adapter operator can cross the JSON boundary."""
        from quantspace.services.sourceflow_adapter import (
            SUPPORTED_OPERATORS,
            can_adapt_factor_candidate,
        )

        for operator in SUPPORTED_OPERATORS:
            candidate = _candidate(
                {
                    "kind": "function",
                    "name": operator,
                    "args": [{"kind": "operand", "name": "paper_signal"}],
                }
            )
            self.assertTrue(can_adapt_factor_candidate(candidate), operator)

    def test_evidence_chunk_ids_are_preserved_in_metadata(self) -> None:
        """Paper evidence metadata crosses the adapter boundary unchanged."""
        from quantspace.services.sourceflow_adapter import (
            adapt_factor_candidate_to_sourceflow_formula,
        )

        candidate = _candidate(
            {"kind": "operand", "name": "paper_signal"},
            metadata_json={"evidence_chunk_ids": [10, 12]},
        )

        formula = adapt_factor_candidate_to_sourceflow_formula(candidate)

        self.assertEqual(formula["metadata"]["evidence_chunk_ids"], [10, 12])

    def test_needs_backtest_is_preserved(self) -> None:
        """The adapter never upgrades candidate validation status."""
        from quantspace.services.sourceflow_adapter import (
            adapt_factor_candidate_to_sourceflow_formula,
        )

        candidate = _candidate({"kind": "operand", "name": "risk_signal"})

        formula = adapt_factor_candidate_to_sourceflow_formula(candidate)

        self.assertEqual(formula["status"], "NEEDS_BACKTEST")
        self.assertFalse(formula["metadata"]["claims_validity"])


def limitations_text(candidate: FactorCandidate) -> str:
    """Return limitations as one searchable string."""
    from quantspace.services.sourceflow_adapter import explain_adapter_limitations

    return "\n".join(explain_adapter_limitations(candidate))


def _candidate(
    expression_json: dict[str, object],
    metadata_json: dict[str, object] | None = None,
) -> FactorCandidate:
    paper = Paper.objects.create(
        title="Adapter paper",
        sha256=f"sha-{Paper.objects.count()}",
    )
    return FactorCandidate.objects.create(
        paper=paper,
        name="AdapterFactor",
        expression_json=expression_json,
        metadata_json=metadata_json or {},
    )
