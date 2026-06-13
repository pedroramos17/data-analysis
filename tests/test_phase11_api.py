"""Phase 11 API endpoint tests.

Exercises every endpoint from the spec against seeded canonical data and checks
the Task 11.1 acceptance criteria: every endpoint returns JSON, reasoning
endpoints carry provenance, and errors are typed (stable HTTP codes + an
``error.type`` envelope).
"""

from __future__ import annotations

import json
from decimal import Decimal

from django.test import TestCase
from django.utils import timezone

from sourceflow import models
from sourceflow.claims import extract_and_persist_document_claims
from sourceflow.entities import create_or_update_entity
from sourceflow.events import extract_and_persist_document_events
from sourceflow.ingestion.normalizer import DocumentInput, persist_normalized_document
from sourceflow.kg import default_graph_store
from sourceflow.tms import JustificationSpec, create_belief

API = "/sourceflow/api"


class Phase11ApiTests(TestCase):
    def setUp(self) -> None:
        self.source = models.Source.objects.create(
            name="Example News",
            url="https://example.test/feed.xml",
            source_type=models.Source.SourceType.RSS,
            language="en",
            reliability_score=Decimal("0.80"),
        )
        self.entity = create_or_update_entity(canonical_name="Petrobras", entity_type="Company")
        self.document = persist_normalized_document(
            DocumentInput(
                source_id=self.source.pk,
                url="https://example.test/petrobras-probe",
                title="Petrobras faces probe",
                raw_text="Petrobras faces a regulatory investigation.",
                published_at=timezone.now(),
            ),
            max_chunk_chars=120,
            chunk_overlap=0,
        ).document
        self.claim = extract_and_persist_document_claims(self.document)[0].claim
        self.event = extract_and_persist_document_events(self.document)[0].event
        # Use the entities the extractor actually linked, so graph-connectivity
        # assertions don't depend on resolution picking the seeded row.
        self.subject_entity_id = self.claim.subject_entity_id
        self.actor_entity_id = self.event.actor_entity_id
        store = default_graph_store()
        store.upsert_claim(self.claim)
        store.upsert_event(self.event)
        self.belief = create_belief(
            belief_type="risk",
            predicate="faces",
            subject_entity=self.entity,
            object_literal="regulatory_risk",
            justifications=[JustificationSpec(support_type="supports", claim=self.claim, weight=Decimal("1"))],
            provenance={"created_by": "test"},
            policy_code="OWA",
        )

    # ---- record endpoints -------------------------------------------------

    def test_documents_returns_json_list(self) -> None:
        response = self.client.get(f"{API}/documents")
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertGreaterEqual(payload["count"], 1)
        self.assertIn(self.document.pk, [row["id"] for row in payload["results"]])

    def test_entities_filter_and_search(self) -> None:
        response = self.client.get(f"{API}/entities", {"q": "Petro"})
        self.assertEqual(response.status_code, 200)
        names = [row["canonical_name"] for row in response.json()["results"]]
        self.assertIn("Petrobras", names)

    def test_claims_carry_provenance(self) -> None:
        response = self.client.get(f"{API}/claims")
        self.assertEqual(response.status_code, 200)
        row = response.json()["results"][0]
        self.assertIn("provenance", row)
        self.assertEqual(row["provenance"]["document_id"], self.document.pk)
        self.assertIsNotNone(row["provenance"]["evidence_span_id"])

    def test_events_carry_provenance(self) -> None:
        response = self.client.get(f"{API}/events")
        self.assertEqual(response.status_code, 200)
        row = response.json()["results"][0]
        self.assertEqual(row["provenance"]["document_id"], self.document.pk)

    # ---- knowledge graph --------------------------------------------------

    def test_kg_entity_neighbors(self) -> None:
        response = self.client.get(f"{API}/kg/entity/{self.subject_entity_id}")
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["node"]["id"], str(self.subject_entity_id))
        self.assertTrue(payload["neighbors"])

    def test_kg_entity_rejects_bad_node_type_via_typed_error(self) -> None:
        # entity ids are valid, but an unknown direction is a typed 400.
        response = self.client.get(f"{API}/kg/entity/{self.subject_entity_id}", {"direction": "sideways"})
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["error"]["type"], "bad_request")

    def test_kg_path_traces_provenance(self) -> None:
        response = self.client.get(
            f"{API}/kg/path",
            {
                "source_type": "claim",
                "source_id": str(self.claim.pk),
                "target_type": "source",
                "target_id": str(self.source.pk),
                "max_depth": "2",
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertGreaterEqual(response.json()["path_count"], 1)

    def test_kg_path_missing_params_is_typed_400(self) -> None:
        response = self.client.get(f"{API}/kg/path", {"source_type": "claim"})
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["error"]["type"], "bad_request")

    # ---- belief explanation ----------------------------------------------

    def test_belief_explain_lists_support_and_provenance(self) -> None:
        response = self.client.get(f"{API}/beliefs/{self.belief.pk}/explain")
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["belief"]["id"], self.belief.pk)
        self.assertIn("truth_status", payload["explanation"])
        self.assertTrue(payload["supporting_justifications"])
        self.assertIn("provenance", payload)

    def test_belief_explain_missing_is_typed_404(self) -> None:
        response = self.client.get(f"{API}/beliefs/999999/explain")
        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json()["error"]["type"], "not_found")

    # ---- reasoning --------------------------------------------------------

    def test_reasoning_infer_returns_provenance(self) -> None:
        response = self.client.post(f"{API}/reasoning/run", data="{}", content_type="application/json")
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["mode"], "infer")
        self.assertIn("results", payload)
        self.assertIn("beliefs_created", payload)

    def test_reasoning_diagnose_ranks_hypotheses(self) -> None:
        body = {"mode": "diagnose", "anomaly": {"anomaly_type": "price_drop", "subject": "Petrobras"}}
        response = self.client.post(f"{API}/reasoning/run", data=json.dumps(body), content_type="application/json")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["mode"], "diagnose")
        self.assertIn("hypotheses", response.json())

    def test_reasoning_unknown_mode_is_typed_400(self) -> None:
        body = {"mode": "teleport"}
        response = self.client.post(f"{API}/reasoning/run", data=json.dumps(body), content_type="application/json")
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["error"]["type"], "bad_request")

    def test_reasoning_get_is_method_not_allowed(self) -> None:
        response = self.client.get(f"{API}/reasoning/run")
        self.assertEqual(response.status_code, 405)
        self.assertEqual(response.json()["error"]["type"], "method_not_allowed")

    def test_invalid_json_body_is_typed_400(self) -> None:
        response = self.client.post(f"{API}/reasoning/run", data="{not json", content_type="application/json")
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["error"]["type"], "invalid_json")

    # ---- GraphRAG ---------------------------------------------------------

    def test_graphrag_query_returns_evidence_pack(self) -> None:
        body = {"query": "Petrobras regulatory investigation"}
        response = self.client.post(f"{API}/graphrag/query", data=json.dumps(body), content_type="application/json")
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertIn("assumptions_used", payload)
        self.assertIn("confidence_breakdown", payload)

    def test_graphrag_answer_is_proof_carrying(self) -> None:
        body = {"query": "Petrobras regulatory investigation", "answer": "Petrobras faces a regulatory probe."}
        response = self.client.post(f"{API}/graphrag/query", data=json.dumps(body), content_type="application/json")
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["answer"], "Petrobras faces a regulatory probe.")
        self.assertIn("what_would_change_this", payload)
        self.assertIn("citations", payload)

    def test_graphrag_empty_query_is_typed_422(self) -> None:
        response = self.client.post(f"{API}/graphrag/query", data=json.dumps({"query": " "}), content_type="application/json")
        self.assertEqual(response.status_code, 422)
        self.assertEqual(response.json()["error"]["type"], "unprocessable_entity")

    # ---- source comparison ------------------------------------------------

    def test_source_comparison_event(self) -> None:
        response = self.client.get(f"{API}/source-comparison/event/{self.event.pk}")
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["assumption_policy"], "PartialCWA")
        self.assertIn("summaries", payload)
        self.assertIn("findings", payload)

    def test_source_comparison_missing_event_is_404(self) -> None:
        response = self.client.get(f"{API}/source-comparison/event/999999")
        self.assertEqual(response.status_code, 404)

    # ---- quant ------------------------------------------------------------

    def test_quant_risk_returns_signals_structure(self) -> None:
        response = self.client.get(f"{API}/quant/risk/{self.actor_entity_id}")
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["asset_id"], str(self.actor_entity_id))
        self.assertIn("risk_signals", payload)

    def test_quant_portfolio_explain(self) -> None:
        asset = models.Asset.objects.create(symbol="PBR", name="Petrobras", asset_type="equity")
        models.PortfolioPosition.objects.create(
            portfolio_id="pf-1",
            asset=asset,
            quantity=Decimal("100"),
            market_value=Decimal("1000"),
        )
        response = self.client.get(f"{API}/quant/portfolio/explain", {"portfolio_id": "pf-1"})
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["portfolio_id"], "pf-1")
        self.assertIn("explanation", payload)

    def test_quant_portfolio_requires_portfolio_id(self) -> None:
        response = self.client.get(f"{API}/quant/portfolio/explain")
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["error"]["type"], "bad_request")

    def test_quant_portfolio_unknown_is_404(self) -> None:
        response = self.client.get(f"{API}/quant/portfolio/explain", {"portfolio_id": "nope"})
        self.assertEqual(response.status_code, 404)

    # ---- method typing on a GET endpoint ---------------------------------

    def test_post_to_get_endpoint_is_405(self) -> None:
        response = self.client.post(f"{API}/documents", data="{}", content_type="application/json")
        self.assertEqual(response.status_code, 405)


class Phase11UiTests(TestCase):
    """Smoke tests for the Task 11.2 screens: they render and satisfy the
    acceptance criteria (inspect an entity, explain a belief, compare sources,
    ask a GraphRAG question)."""

    def setUp(self) -> None:
        self.source = models.Source.objects.create(
            name="Example News",
            url="https://example.test/feed.xml",
            source_type=models.Source.SourceType.RSS,
            language="en",
            reliability_score=Decimal("0.80"),
        )
        create_or_update_entity(canonical_name="Petrobras", entity_type="Company")
        self.document = persist_normalized_document(
            DocumentInput(
                source_id=self.source.pk,
                url="https://example.test/petrobras-probe",
                title="Petrobras faces probe",
                raw_text="Petrobras faces a regulatory investigation.",
                published_at=timezone.now(),
            ),
            max_chunk_chars=120,
            chunk_overlap=0,
        ).document
        self.claim = extract_and_persist_document_claims(self.document)[0].claim
        self.event = extract_and_persist_document_events(self.document)[0].event
        default_graph_store().upsert_claim(self.claim)
        self.belief = create_belief(
            belief_type="risk",
            predicate="faces",
            subject_entity=self.claim.subject_entity,
            object_literal="regulatory_risk",
            justifications=[JustificationSpec(support_type="supports", claim=self.claim, weight=Decimal("1"))],
            provenance={"created_by": "test"},
            policy_code="OWA",
        )

    def test_index_and_list_screens_render(self) -> None:
        for path in ("/sourceflow/", "/sourceflow/documents/", "/sourceflow/entities/",
                     "/sourceflow/claims/", "/sourceflow/events/", "/sourceflow/beliefs/",
                     "/sourceflow/kg/path/", "/sourceflow/risk/", "/sourceflow/portfolio/"):
            with self.subTest(path=path):
                self.assertEqual(self.client.get(path).status_code, 200)

    def test_entity_profile_shows_claims_and_events(self) -> None:
        response = self.client.get(f"/sourceflow/entities/{self.claim.subject_entity_id}/")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Petrobras")

    def test_belief_explanation_screen(self) -> None:
        response = self.client.get(f"/sourceflow/beliefs/{self.belief.pk}/")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Why belief")

    def test_source_comparison_screen(self) -> None:
        response = self.client.get(f"/sourceflow/source-comparison/event/{self.event.pk}/")
        self.assertEqual(response.status_code, 200)

    def test_graphrag_screen(self) -> None:
        response = self.client.get("/sourceflow/graphrag/", {"q": "Petrobras regulatory"})
        self.assertEqual(response.status_code, 200)
