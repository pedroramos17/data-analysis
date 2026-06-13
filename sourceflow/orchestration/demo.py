"""Phase 15 end-to-end demo.

Runs the whole neurosymbolic flow over one scenario -- a cluster of articles
about a company facing a regulatory investigation -- and returns a structured,
JSON-able report with the ten required outputs plus the Definition-of-Done
invariants (every conclusion has evidence, every belief has justification, every
risk path is auditable, contradictions are preserved rather than collapsed).

This is wiring, not new capability: it composes the Phase 1-14 modules. It is
the single entry point behind the ``demo_e2e`` management command.
"""

from __future__ import annotations

import dataclasses
from decimal import Decimal
from typing import Any


def _jsonable(value: Any) -> Any:
    if dataclasses.is_dataclass(value) and not isinstance(value, type):
        return {k: _jsonable(v) for k, v in dataclasses.asdict(value).items()}
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, (list, tuple)):
        return [_jsonable(v) for v in value]
    if isinstance(value, dict):
        return {str(k): _jsonable(v) for k, v in value.items()}
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return value


# One scenario cluster: four sources covering the same regulatory event.
# Wire A/B assert it (negative), Corporate Wire disputes it (positive stance),
# Regional Daily reports the event but omits the claim (omission under PartialCWA).
_ARTICLES = [
    {"source": "Wire A", "owner": "Wire Co", "reliability": "0.92", "polarity": "negative", "claim": True},
    {"source": "Wire B", "owner": "Wire Co", "reliability": "0.88", "polarity": "negative", "claim": True},
    {"source": "Corporate Wire", "owner": "Petrobras IR", "reliability": "0.55", "polarity": "positive", "claim": True},
    {"source": "Regional Daily", "owner": "Regional Co", "reliability": "0.70", "polarity": "negative", "claim": False},
]
_TEXT = "Petrobras faces a regulatory investigation."
_QUESTION = "What regulatory risk does Petrobras face?"


def run_end_to_end_demo() -> dict[str, Any]:
    from django.utils import timezone

    from sourceflow.claims import ClaimCandidate, compare_event_cluster_claims, persist_claim_candidates
    from sourceflow.entities import create_or_update_entity, extract_link_and_persist_document_mentions
    from sourceflow.events import cluster_events, extract_and_persist_document_events
    from sourceflow.graphrag import hybrid_retrieve
    from sourceflow.ingestion.normalizer import DocumentInput, persist_normalized_document
    from sourceflow.kg import default_graph_store, node_ref
    from sourceflow import models
    from sourceflow.quant import RiskGraph, explain_portfolio_risk
    from sourceflow.reasoning.contradictions import detect_claim_contradictions
    from sourceflow.tms import JustificationSpec, create_belief

    store = default_graph_store()

    # --- scenario fixtures: company, supplier (with KG relation), asset, book ---
    company = create_or_update_entity(canonical_name="Petrobras", entity_type="Company", sector="energy")
    supplier = create_or_update_entity(canonical_name="SupplierCo", entity_type="Company", sector="industrial")
    store.add_edge(
        node_ref("entity", supplier.pk), node_ref("entity", company.pk), "supplies_to",
        confidence=Decimal("0.90"), provenance={"created_by": "demo", "relation": "supplier"},
    )
    asset = models.Asset.objects.create(
        symbol="PETR4", name="Petrobras PN", sector="energy", currency="BRL",
        external_ids_json={"entity_id": company.pk},
    )
    position = models.PortfolioPosition.objects.create(
        portfolio_id="demo-book", asset=asset, quantity=Decimal("100"), market_value=Decimal("10000"), currency="BRL",
    )

    documents, events, claims, mention_count = [], [], [], 0
    for index, article in enumerate(_ARTICLES):
        owner, _ = models.ProviderOwner.objects.get_or_create(
            name=article["owner"], defaults={"canonical_name": article["owner"]}
        )
        source, _ = models.Source.objects.get_or_create(
            name=article["source"],
            defaults={
                "url": f"https://example.test/{index}",
                "source_type": models.Source.SourceType.RSS,
                "language": "en",
                "reliability_score": Decimal(article["reliability"]),
                "bias_tags": ["business"],
                "provider_owner": owner,
            },
        )
        # 1. ingest (+ normalize + chunk)
        document = persist_normalized_document(
            DocumentInput(
                source_id=source.pk, url=f"https://example.test/article-{index}",
                title=f"{article['source']} on Petrobras", raw_text=_TEXT, published_at=timezone.now(),
            ),
            max_chunk_chars=120, chunk_overlap=0,
        ).document
        documents.append((document, source))
        # 2. entity linking
        mention_count += len(extract_link_and_persist_document_mentions(document))
        # 4. event creation (every source reports the event)
        event = extract_and_persist_document_events(document)[0].event
        events.append(event)
        store.upsert_event(event)
        # 3. claim extraction (controlled polarity; Regional omits the claim)
        if article["claim"]:
            claim = persist_claim_candidates(
                document,
                [ClaimCandidate(
                    subject_text="Petrobras", predicate="faces", object_text="a regulatory investigation",
                    object_literal="a regulatory investigation", polarity=article["polarity"],
                    confidence=Decimal("0.85"), evidence_text=_TEXT,
                )],
            )[0].claim
            claims.append((claim, source))
            store.upsert_claim(claim)

    negative_claim = next(c for c, _ in claims if c.polarity == "negative")
    positive_claim = next(c for c, _ in claims if c.polarity == "positive")

    # 5. source comparison over the event cluster
    cluster = cluster_events(events, claims=[c for c, _ in claims])[0]
    comparison = compare_event_cluster_claims(
        cluster,
        expected_sources=[s for _, s in documents],
        group_by=("owner",),
    )

    # contradiction handling: preserve both stances, never collapse
    detect_claim_contradictions([c for c, _ in claims])

    # 6 + 7. risk belief inferred, with BOTH supporting and contradicting
    # justifications -> truth status stays disputed (not collapsed).
    belief = create_belief(
        belief_type="risk",
        predicate="increases",
        subject_entity=company,
        object_literal="regulatory_risk",
        justifications=[
            JustificationSpec("supports", claim=negative_claim),
            JustificationSpec("contradicts", claim=positive_claim),
        ],
        provenance={"created_by": "sourceflow.orchestration.demo", "event": "regulatory_investigation"},
        policy_code="OWA",
    )

    # 8. risk propagation to actor, supplier, and portfolio (auditable paths)
    risk_graph = RiskGraph(graph_store=store)
    direct_signals: list[Any] = []
    for event in events:
        direct_signals.extend(risk_graph.propagate_event_risk(event))
    propagated: list[Any] = []
    for signal in direct_signals:
        propagated.extend(risk_graph.propagate_supplier_customer_risk(signal))
    aggregates = risk_graph.aggregate_portfolio_risk("demo-book", [*direct_signals, *propagated], positions=[position])

    # 9. GraphRAG proof-carrying answer (refuses to answer without evidence)
    pack = hybrid_retrieve(_QUESTION, limit=10)
    answer = pack.to_answer(
        "Petrobras faces regulatory-investigation risk; coverage is disputed by a low-reliability source.",
    )

    # 10. portfolio exposure explanation
    explanation = explain_portfolio_risk("demo-book", aggregates=aggregates, positions=[position])

    report = _build_report(
        documents=documents, mention_count=mention_count, claims=claims, events=events,
        comparison=comparison, belief=belief, pack=pack, answer=answer,
        direct_signals=direct_signals, propagated=propagated, aggregates=aggregates, explanation=explanation,
    )
    report["invariants"] = _invariants(belief, aggregates, pack)
    return report


def _build_report(*, documents, mention_count, claims, events, comparison, belief, pack, answer,
                  direct_signals, propagated, aggregates, explanation) -> dict[str, Any]:
    return {
        "scenario": "A cluster of articles about a company facing a regulatory investigation.",
        "steps": {
            "1_documents_ingested": [
                {"document_id": d.pk, "source": s.name, "title": d.title} for d, s in documents
            ],
            "2_entities_linked": {"mentions_linked": mention_count},
            "3_claims_extracted": [
                {"claim_id": c.pk, "subject": c.subject_entity.canonical_name, "predicate": c.predicate,
                 "polarity": c.polarity, "source": s.name, "evidence_span_id": c.evidence_span_id}
                for c, s in claims
            ],
            "4_event_created": {
                "event_id": events[0].pk, "actor": events[0].actor_entity.canonical_name,
                "event_type": events[0].event_type, "evidence_span_id": events[0].evidence_span_id,
                "count": len(events),
            },
            "5_source_comparison": {
                "cluster_id": comparison.cluster_id,
                "assumption_policy": comparison.assumption_policy,
                "summaries": [_jsonable(s) for s in comparison.summaries],
                "findings": [_jsonable(f) for f in comparison.findings],
                "omissions": [_jsonable(o) for o in comparison.omissions],
            },
            "6_risk_belief": {
                "belief_id": belief.pk, "belief_type": belief.belief_type, "predicate": belief.predicate,
                "object": belief.object_literal, "truth_status": belief.truth_status,
                "confidence": float(belief.confidence), "assumption_policy": belief.assumption_policy.code,
                "justification_count": belief.justifications.count(),
            },
            "7_supporting_and_contradicting_evidence": {
                "supporting": [
                    {"support_type": j.support_type, "claim_id": j.supporting_claim_id}
                    for j in belief.justifications.all() if j.support_type != "contradicts"
                ],
                "contradicting": [
                    {"support_type": j.support_type, "claim_id": j.supporting_claim_id}
                    for j in belief.justifications.all() if j.support_type == "contradicts"
                ],
            },
            "8_risk_propagated": {
                "direct_signals": [_jsonable(s) for s in direct_signals],
                "propagated_to_suppliers": [_jsonable(s) for s in propagated],
                "portfolio_aggregates": [_jsonable(a) for a in aggregates],
            },
            "9_graphrag_answer": answer,
            "10_portfolio_explanation": _jsonable(explanation),
        },
    }


def _invariants(belief, aggregates, pack) -> dict[str, bool]:
    from sourceflow.models import Belief

    every_belief_has_justification = all(
        b.justifications.exists() for b in Belief.objects.all()
    )
    # auditable = each portfolio risk contributor carries a graph path AND source evidence
    risk_paths_auditable = bool(aggregates) and all(
        contributor.graph_path and contributor.source_evidence
        for aggregate in aggregates
        for contributor in aggregate.contributors
    )
    return {
        "every_belief_has_justification": every_belief_has_justification,
        "every_conclusion_has_evidence": pack.has_evidence,
        "graphrag_answer_carries_evidence": bool(pack.supporting_claims),
        "contradiction_preserved_not_collapsed": belief.truth_status == Belief.TruthStatus.CONTRADICTED,
        "every_risk_path_auditable": risk_paths_auditable,
    }
