"""Phase 10 Quant 4.0 reasoning persistence tests."""

from __future__ import annotations

from decimal import Decimal

from django.test import TestCase
from django.utils import timezone

from sourceflow import models
from sourceflow.entities import create_or_update_entity
from sourceflow.events import extract_and_persist_document_events
from sourceflow.ingestion.normalizer import DocumentInput, persist_normalized_document
from sourceflow.kg import default_graph_store, node_ref
from sourceflow.quant import (
    RiskGraph,
    RuleBasedRegimeDetector,
    build_feature_matrix,
    explain_portfolio_risk,
    generate_event_alpha_candidates,
)


class Phase10QuantReasoningTests(TestCase):
    def setUp(self) -> None:
        self.company = create_or_update_entity(canonical_name="Petrobras", entity_type="Company", sector="energy")
        self.supplier = create_or_update_entity(canonical_name="SupplierCo", entity_type="Company", sector="industrial")
        self.source = self._source("Wire A", reliability="0.90")

    def test_risk_graph_direct_relation_and_portfolio_aggregation(self) -> None:
        document = self._document(self.source, "Petrobras lawsuit risk", "Petrobras faces a lawsuit.")
        event = extract_and_persist_document_events(document)[0].event
        store = default_graph_store()
        store.add_edge(
            node_ref("entity", self.supplier.pk),
            node_ref("entity", self.company.pk),
            "supplies_to",
            confidence=Decimal("0.90"),
            provenance={"created_by": "test", "relation": "supplier"},
        )
        asset = models.Asset.objects.create(
            symbol="PETR4",
            name="Petrobras PN",
            country="BR",
            sector="energy",
            currency="BRL",
            external_ids_json={"entity_id": self.company.pk},
        )
        position = models.PortfolioPosition.objects.create(
            portfolio_id="book-1",
            asset=asset,
            quantity=Decimal("100"),
            market_value=Decimal("10000"),
            currency="BRL",
        )

        graph = RiskGraph(graph_store=store)
        direct = graph.propagate_event_risk(event)
        propagated = graph.propagate_supplier_customer_risk(next(signal for signal in direct if signal.risk_type == "legal_risk"))
        aggregates = graph.aggregate_portfolio_risk("book-1", [*direct, *propagated], positions=[position])

        self.assertIn("legal_risk", {signal.risk_type for signal in direct})
        self.assertTrue(propagated)
        self.assertEqual(propagated[0].subject_id, str(self.supplier.pk))
        self.assertTrue(aggregates)
        self.assertTrue(aggregates[0].contributors[0].source_evidence)
        self.assertTrue(aggregates[0].contributors[0].graph_path)

    def test_event_alpha_candidate_uses_reliability_and_sector_reaction(self) -> None:
        document = self._document(self.source, "Petrobras regulatory risk", "Petrobras faces a regulatory investigation.")
        event = extract_and_persist_document_events(document)[0].event

        candidates = generate_event_alpha_candidates([event], sector_reactions={"energy": Decimal("-0.03")})

        self.assertEqual(len(candidates), 1)
        self.assertEqual(candidates[0].direction, "short")
        self.assertTrue(candidates[0].reasoning_trail)
        self.assertTrue(candidates[0].to_backtest_spec()["requires_no_live_trading"])

    def test_regime_detector_links_to_belief_and_flags_recompute(self) -> None:
        belief = models.Belief.objects.create(
            belief_type="risk",
            predicate="increases",
            object_literal="legal_risk",
            assumption_policy=models.AssumptionPolicy.objects.create(code="OWA", name="Open-world assumption"),
            provenance_json={"created_by": "test"},
        )
        matrix = build_feature_matrix(
            [
                {"volatility": "0.1", "liquidity": "0.9", "return": "0.01", "kg_risk": "0.1"},
                {"volatility": "0.9", "liquidity": "0.2", "return": "-0.05", "kg_risk": "0.7"},
            ]
        )

        result = RuleBasedRegimeDetector().detect(matrix, linked_beliefs=(belief,))

        self.assertIn(str(belief.pk), result.linked_belief_ids)
        self.assertTrue(result.regime_probabilities)
        self.assertTrue(result.trigger_risk_recompute)

    def test_portfolio_explanation_includes_evidence_assumptions_and_hedges(self) -> None:
        document = self._document(self.source, "Petrobras lawsuit risk", "Petrobras faces a lawsuit.")
        event = extract_and_persist_document_events(document)[0].event
        asset = models.Asset.objects.create(
            symbol="PETR4",
            external_ids_json={"entity_id": self.company.pk},
            sector="energy",
            currency="BRL",
        )
        position = models.PortfolioPosition.objects.create(
            portfolio_id="book-1",
            asset=asset,
            quantity=Decimal("100"),
            market_value=Decimal("10000"),
            currency="BRL",
        )
        graph = RiskGraph()
        aggregates = graph.aggregate_portfolio_risk("book-1", graph.propagate_event_risk(event), positions=[position])

        explanation = explain_portfolio_risk("book-1", aggregates=aggregates, positions=[position])

        self.assertTrue(explanation.top_risk_contributors)
        contribution = explanation.top_risk_contributors[0]
        self.assertEqual(contribution.asset, "PETR4")
        self.assertTrue(contribution.source_evidence)
        self.assertTrue(contribution.graph_paths)
        self.assertTrue(contribution.assumptions_used)
        self.assertTrue(contribution.suggested_hedge_candidates)

    def _source(self, name: str, *, reliability: str) -> models.Source:
        return models.Source.objects.create(
            name=name,
            url=f"https://example.test/{name.lower().replace(' ', '-')}.xml",
            source_type=models.Source.SourceType.RSS,
            country="BR",
            language="en",
            reliability_score=reliability,
            bias_tags=["business"],
        )

    def _document(self, source: models.Source, title: str, text: str) -> models.Document:
        result = persist_normalized_document(
            DocumentInput(
                source_id=source.pk,
                url=f"https://example.test/phase10-{models.Document.objects.count()}",
                title=title,
                raw_text=text,
                published_at=timezone.now(),
            ),
            max_chunk_chars=120,
            chunk_overlap=0,
        )
        return result.document
