"""Phase 12 Task 12.2 -- required reasoning-behavior tests.

One test per required behavior:

* CWA does not apply to news by default.
* OWA does not infer false from missing news.
* PartialCWA detects source omission.
* Contradictory claims do not crash inference.
* Retraction updates dependent beliefs.
* Risk propagation creates an auditable graph path.
* GraphRAG includes supporting and contradicting evidence.
"""

from __future__ import annotations

from decimal import Decimal

from django.test import TestCase
from django.utils import timezone

from sourceflow import models
from sourceflow.claims import ClaimCandidate, compare_event_cluster_claims, persist_claim_candidates
from sourceflow.entities import create_or_update_entity
from sourceflow.events import cluster_events, extract_and_persist_document_events
from sourceflow.graphrag import HybridGraphRAGRetriever
from sourceflow.ingestion.normalizer import DocumentInput, persist_normalized_document
from sourceflow.kg import default_graph_store, node_ref
from sourceflow.quant import RiskGraph
from sourceflow.reasoning import InferenceEngine, RuleDefinition
from sourceflow.reasoning.assumptions import (
    AssumptionPolicyCode,
    evaluate_missing_fact,
    resolve_assumption_policy,
)
from sourceflow.reasoning.contradictions import detect_claim_contradictions
from sourceflow.tms import JustificationSpec, create_belief, retract_claim

PROVENANCE = {"created_by": "sourceflow.tests.test_phase12_reasoning"}


class Phase12ReasoningTests(TestCase):
    def setUp(self) -> None:
        self.entity = create_or_update_entity(canonical_name="Petrobras", entity_type="Company")

    # 1 --------------------------------------------------------------------
    def test_cwa_does_not_apply_to_news_by_default(self) -> None:
        for context in ("news", "article", "document", "source_claim"):
            self.assertEqual(resolve_assumption_policy(context), AssumptionPolicyCode.OWA)
        # Controlled internal tables DO default to CWA -- the contrast that
        # makes the news default meaningful.
        for context in ("trade", "portfolio_position", "job"):
            self.assertEqual(resolve_assumption_policy(context), AssumptionPolicyCode.CWA)

    # 2 --------------------------------------------------------------------
    def test_owa_does_not_infer_false_from_missing_news(self) -> None:
        owa = evaluate_missing_fact(AssumptionPolicyCode.OWA)
        self.assertFalse(owa.can_infer_absence)
        self.assertEqual(owa.truth_status, "unknown")
        # A controlled closed-world table can infer absence -- the distinction.
        cwa = evaluate_missing_fact(AssumptionPolicyCode.CWA)
        self.assertTrue(cwa.can_infer_absence)

    # 3 --------------------------------------------------------------------
    def test_partial_cwa_detects_source_omission(self) -> None:
        wire_owner = models.ProviderOwner.objects.create(name="Wire Co", canonical_name="Wire Co")
        regional_owner = models.ProviderOwner.objects.create(name="Regional Co", canonical_name="Regional Co")
        wire = self._source("Wire A", wire_owner)
        regional = self._source("Regional", regional_owner)
        wire_doc = self._document("Petrobras faces a lawsuit.", source=wire)
        regional_doc = self._document("Petrobras faces a lawsuit.", source=regional)
        wire_event = extract_and_persist_document_events(wire_doc)[0].event
        regional_event = extract_and_persist_document_events(regional_doc)[0].event
        wire_claim = self._claim(wire_doc, polarity="negative", predicate="faces", object_literal="lawsuit")
        cluster = cluster_events([wire_event, regional_event], claims=[wire_claim])[0]

        comparison = compare_event_cluster_claims(
            cluster, expected_sources=[wire, regional], group_by=("owner",)
        )

        self.assertEqual(comparison.assumption_policy, "PartialCWA")
        self.assertTrue(comparison.omissions)
        omission = comparison.omissions[0]
        self.assertIn("source omitted", omission.description)
        self.assertFalse(omission.inferred_false)  # omission != falsity
        self.assertEqual(omission.assumption_policy, "PartialCWA")

    # 4 --------------------------------------------------------------------
    def test_contradictory_claims_do_not_crash_inference(self) -> None:
        positive = self._claim(self._document("Petrobras reports profit growth."), polarity="positive",
                               predicate="reports", object_literal="profit growth")
        negative = self._claim(self._document("Petrobras reports profit growth."), polarity="negative",
                               predicate="reports", object_literal="profit growth")
        detect_claim_contradictions([positive, negative])
        positive.refresh_from_db()
        negative.refresh_from_db()
        rule = RuleDefinition.from_mapping(
            {
                "id": "profit_growth_increases_risk_appetite",
                "type": "deductive",
                "when": [{"predicate": "reports"}, {"polarity": "positive"}],
                "then": [{"belief_type": "risk", "predicate": "decreases", "object": "risk_aversion"}],
            }
        )

        # No exception, both claims preserved, no hard belief derived from disputed support.
        results = InferenceEngine([rule]).infer_from_support(positive)

        self.assertEqual([r.status for r in results], ["skipped_contradicted_support"])
        self.assertEqual(models.Belief.objects.count(), 0)
        self.assertEqual(models.Claim.objects.filter(status=models.Claim.Status.DISPUTED).count(), 2)

    # 5 --------------------------------------------------------------------
    def test_retraction_updates_dependent_beliefs(self) -> None:
        claim = self._claim(self._document("Petrobras faces a regulatory investigation."),
                            polarity="negative", predicate="faces", object_literal="regulatory investigation")
        belief = create_belief(
            belief_type="risk_exposure",
            predicate="under_regulatory_investigation",
            subject_entity=claim.subject_entity,
            justifications=[JustificationSpec("supports", claim=claim)],
            provenance=PROVENANCE,
        )
        self.assertEqual(belief.status, models.Belief.Status.ACTIVE)

        result = retract_claim(claim, reason="source correction", provenance=PROVENANCE)

        belief.refresh_from_db()
        self.assertEqual(belief.status, models.Belief.Status.STALE)
        self.assertIn(belief.pk, [b.pk for b in result.stale_beliefs])
        self.assertTrue(models.RetractionLog.objects.filter(target_type="claim").exists())

    # 6 --------------------------------------------------------------------
    def test_risk_propagation_creates_auditable_graph_path(self) -> None:
        supplier = create_or_update_entity(canonical_name="SupplierCo", entity_type="Company", sector="industrial")
        document = self._document("Petrobras faces a lawsuit.")
        event = extract_and_persist_document_events(document)[0].event
        store = default_graph_store()
        store.add_edge(
            node_ref("entity", supplier.pk),
            node_ref("entity", self.entity.pk),
            "supplies_to",
            confidence=Decimal("0.90"),
            provenance={"created_by": "test", "relation": "supplier"},
        )
        asset = models.Asset.objects.create(symbol="PETR4", sector="energy", currency="BRL",
                                            external_ids_json={"entity_id": self.entity.pk})
        position = models.PortfolioPosition.objects.create(
            portfolio_id="book-1", asset=asset, quantity=Decimal("100"), market_value=Decimal("10000"),
        )

        graph = RiskGraph(graph_store=store)
        direct = graph.propagate_event_risk(event)
        legal = next(signal for signal in direct if signal.risk_type == "legal_risk")
        propagated = graph.propagate_supplier_customer_risk(legal)
        aggregates = graph.aggregate_portfolio_risk("book-1", [*direct, *propagated], positions=[position])

        self.assertTrue(legal.explanation)  # human-readable reasoning
        self.assertTrue(propagated)
        self.assertEqual(propagated[0].subject_id, str(supplier.pk))  # propagated through the edge
        self.assertTrue(aggregates[0].contributors[0].graph_path)  # auditable path
        self.assertTrue(aggregates[0].contributors[0].source_evidence)  # back to source

    # 7 --------------------------------------------------------------------
    def test_graphrag_includes_supporting_and_contradicting_evidence(self) -> None:
        source = self._source("Wire A", None)
        counter = self._source("Counter B", None)
        document = self._document("Petrobras faces a lawsuit risk after court filing.", source=source)
        counter_document = self._document("Petrobras faces a lawsuit risk after court filing.", source=counter)
        event = extract_and_persist_document_events(document)[0].event
        claim = self._claim(document, polarity="negative", predicate="faces", object_literal="lawsuit risk")
        counterclaim = self._claim(counter_document, polarity="positive", predicate="faces", object_literal="lawsuit risk")
        detect_claim_contradictions([claim, counterclaim])
        store = default_graph_store()
        store.upsert_claim(claim)
        store.upsert_claim(counterclaim)
        store.upsert_event(event)

        pack = HybridGraphRAGRetriever().retrieve("What is the Petrobras lawsuit risk?")

        self.assertTrue(pack.supporting_claims)
        self.assertTrue(pack.contradicting_claims)  # contradictions are not hidden

    # helpers --------------------------------------------------------------
    def _source(self, name: str, owner: models.ProviderOwner | None) -> models.Source:
        return models.Source.objects.create(
            name=name,
            url=f"https://example.test/{name.lower().replace(' ', '-')}.xml",
            provider_owner=owner,
            source_type=models.Source.SourceType.RSS,
            country="BR",
            language="en",
            reliability_score=Decimal("0.80"),
            bias_tags=["business"],
        )

    def _document(self, text: str, *, source: models.Source | None = None) -> models.Document:
        if source is None:
            source, _ = models.Source.objects.get_or_create(
                name="Example News",
                defaults={
                    "url": "https://example.test/feed.xml",
                    "source_type": models.Source.SourceType.RSS,
                    "language": "en",
                },
            )
        result = persist_normalized_document(
            DocumentInput(
                source_id=source.pk,
                url=f"https://example.test/phase12-{models.Document.objects.count()}",
                title="Phase 12 reasoning",
                raw_text=text,
                published_at=timezone.now(),
            ),
            max_chunk_chars=200,
            chunk_overlap=0,
        )
        return result.document

    def _claim(self, document: models.Document, *, polarity: str, predicate: str, object_literal: str) -> models.Claim:
        return persist_claim_candidates(
            document,
            [
                ClaimCandidate(
                    subject_text="Petrobras",
                    predicate=predicate,
                    object_text=object_literal,
                    object_literal=object_literal,
                    polarity=polarity,
                    confidence=Decimal("0.80"),
                    evidence_text=document.clean_text or document.raw_text,
                )
            ],
        )[0].claim
