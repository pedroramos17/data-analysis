"""Server-rendered Phase 11 UI screens.

These views read the canonical knowledge layer (and the Phase 7-10 reasoning /
comparison / GraphRAG / quant services) directly and render compact templates.
They are intentionally thin -- the JSON API in :mod:`sourceflow.api` is the
machine surface; this is the minimal human surface that satisfies the Task 11.2
acceptance criteria: inspect an entity and see its claims/events, inspect a
belief and see why it exists, compare source coverage, and ask a GraphRAG
question and see the evidence.
"""

from __future__ import annotations

from typing import Any

from django.db.models import Q
from django.shortcuts import render


def index(request):
    from sourceflow.models import Belief, Claim, Document, Entity, Event

    counts = {
        "documents": Document.objects.count(),
        "entities": Entity.objects.count(),
        "claims": Claim.objects.count(),
        "events": Event.objects.count(),
        "beliefs": Belief.objects.count(),
    }
    return render(request, "sourceflow/index.html", {"counts": counts})


def document_explorer(request):
    from sourceflow.models import Document

    documents = list(Document.objects.select_related("source").all()[:100])
    return render(request, "sourceflow/documents.html", {"documents": documents})


def entity_list(request):
    from sourceflow.models import Entity

    query = request.GET.get("q", "").strip()
    entities = Entity.objects.all()
    if query:
        entities = entities.filter(canonical_name__icontains=query)
    return render(request, "sourceflow/entities.html", {"entities": list(entities[:100]), "q": query})


def entity_profile(request, entity_id: int):
    """Entity profile: the entity plus every claim and event that mentions it."""
    from sourceflow.models import Claim, Entity, Event

    entity = Entity.objects.filter(pk=entity_id).first()
    if entity is None:
        return render(request, "sourceflow/entity_detail.html", {"entity": None, "entity_id": entity_id})
    claims = list(
        Claim.objects.select_related("source", "document")
        .filter(Q(subject_entity_id=entity_id) | Q(object_entity_id=entity_id))[:100]
    )
    events = list(
        Event.objects.select_related("source", "document")
        .filter(Q(actor_entity_id=entity_id) | Q(object_entity_id=entity_id))[:100]
    )
    return render(
        request,
        "sourceflow/entity_detail.html",
        {"entity": entity, "claims": claims, "events": events},
    )


def claim_explorer(request):
    from sourceflow.models import Claim

    claims = list(Claim.objects.select_related("subject_entity", "object_entity", "source", "evidence_span").all()[:100])
    return render(request, "sourceflow/claims.html", {"claims": claims})


def event_clusters(request):
    from sourceflow.events import cluster_events
    from sourceflow.models import Claim, Event

    events = list(Event.objects.select_related("actor_entity", "source", "document").all()[:200])
    claims = list(Claim.objects.select_related("source", "document").all()[:200])
    clusters = cluster_events(events, claims=claims)
    return render(request, "sourceflow/event_clusters.html", {"clusters": clusters})


def source_comparison(request, event_id: int | None = None):
    """Pick an event, then show how each source group covered its cluster."""
    from sourceflow.claims import compare_event_cluster_claims
    from sourceflow.events import cluster_events, event_cluster_key
    from sourceflow.models import Claim, Event, Source

    if event_id is None:
        events = list(Event.objects.select_related("actor_entity").all()[:100])
        return render(request, "sourceflow/source_comparison.html", {"events": events, "comparison": None})

    event = Event.objects.select_related("actor_entity").filter(pk=event_id).first()
    if event is None:
        return render(request, "sourceflow/source_comparison.html", {"events": [], "comparison": None, "missing": event_id})

    target_key = event_cluster_key(event)
    sibling_events = list(
        Event.objects.select_related("source", "document", "actor_entity").filter(
            actor_entity_id=event.actor_entity_id, event_type=event.event_type
        )
    )
    related_claims = list(
        Claim.objects.select_related("source", "document").filter(subject_entity_id=event.actor_entity_id)
    )
    clusters = cluster_events(sibling_events, claims=related_claims)
    cluster = next((c for c in clusters if c.key == target_key), clusters[0] if clusters else None)
    comparison = None
    if cluster is not None:
        comparison = compare_event_cluster_claims(
            cluster,
            claims=related_claims,
            expected_sources=list(Source.objects.all()),
            group_by=("owner",),
        )
    return render(
        request,
        "sourceflow/source_comparison.html",
        {"events": [], "comparison": comparison, "event": event},
    )


def kg_path_view(request):
    """Knowledge graph path view: walk edges between two nodes."""
    from sourceflow.kg import GraphSchemaError, default_graph_store, node_ref

    params = {key: request.GET.get(key, "") for key in ("source_type", "source_id", "target_type", "target_id")}
    paths: list[list[Any]] = []
    error = ""
    submitted = all(params.values())
    if submitted:
        try:
            start = node_ref(params["source_type"], params["source_id"])
            end = node_ref(params["target_type"], params["target_id"])
            paths = default_graph_store().find_paths(start, end, max_depth=int(request.GET.get("max_depth", 3) or 3))
        except GraphSchemaError as exc:
            error = str(exc)
        except ValueError as exc:
            error = str(exc)
    return render(
        request,
        "sourceflow/kg_path.html",
        {"params": params, "paths": paths, "submitted": submitted, "error": error},
    )


def belief_list(request):
    from sourceflow.models import Belief

    beliefs = list(Belief.objects.select_related("assumption_policy", "subject_entity").all()[:100])
    return render(request, "sourceflow/beliefs.html", {"beliefs": beliefs})


def belief_explanation(request, belief_id: int):
    """Belief explanation view: why this belief exists -- support and contradiction."""
    from sourceflow.models import Belief
    from sourceflow.tms import CONTRADICTING_TYPES, justification_is_active, recompute_belief

    belief = (
        Belief.objects.select_related("assumption_policy", "created_by_rule", "subject_entity")
        .filter(pk=belief_id)
        .first()
    )
    if belief is None:
        return render(request, "sourceflow/belief_detail.html", {"belief": None, "belief_id": belief_id})

    recompute_belief(belief)
    supporting: list[Any] = []
    contradicting: list[Any] = []
    for justification in belief.justifications.select_related(
        "supporting_claim", "supporting_event", "supporting_belief", "rule"
    ).all():
        row = {"justification": justification, "active": justification_is_active(justification)}
        if justification.support_type in CONTRADICTING_TYPES:
            contradicting.append(row)
        else:
            supporting.append(row)
    return render(
        request,
        "sourceflow/belief_detail.html",
        {"belief": belief, "supporting": supporting, "contradicting": contradicting},
    )


def graphrag_query_view(request):
    """GraphRAG query screen: ask a question and see proof-carrying evidence."""
    from sourceflow.graphrag import hybrid_retrieve

    query = request.GET.get("q", "").strip()
    pack = None
    if query:
        pack = hybrid_retrieve(query, limit=10).to_dict()
    return render(request, "sourceflow/graphrag.html", {"q": query, "pack": pack})


def risk_view(request, asset_id: int | None = None):
    """Risk graph view: propagated risk signals for an entity."""
    from sourceflow.models import Entity, Event
    from sourceflow.quant import RiskGraph

    if asset_id is None:
        entities = list(Entity.objects.all()[:100])
        return render(request, "sourceflow/risk.html", {"entities": entities, "signals": None})

    entity = Entity.objects.filter(pk=asset_id).first()
    events = list(Event.objects.filter(actor_entity_id=asset_id).order_by("-event_time")[:50])
    risk_graph = RiskGraph()
    signals: list[Any] = []
    for event in events:
        direct = risk_graph.propagate_event_risk(event)
        signals.extend(direct)
        for base_signal in direct:
            signals.extend(risk_graph.propagate_supplier_customer_risk(base_signal))
    return render(request, "sourceflow/risk.html", {"entity": entity, "signals": signals, "asset_id": asset_id})


def portfolio_view(request):
    """Portfolio explanation view: top risk contributors for a portfolio."""
    from sourceflow.models import Event, PortfolioPosition
    from sourceflow.quant import RiskGraph, explain_portfolio_risk

    portfolio_id = request.GET.get("portfolio_id", "").strip()
    portfolios = list(
        PortfolioPosition.objects.values_list("portfolio_id", flat=True).distinct()[:50]
    )
    explanation = None
    if portfolio_id:
        positions = list(PortfolioPosition.objects.select_related("asset").filter(portfolio_id=portfolio_id))
        if positions:
            risk_graph = RiskGraph()
            signals: list[Any] = []
            for event in Event.objects.order_by("-event_time")[:100]:
                direct = risk_graph.propagate_event_risk(event)
                signals.extend(direct)
                for base_signal in direct:
                    signals.extend(risk_graph.propagate_supplier_customer_risk(base_signal))
            aggregates = risk_graph.aggregate_portfolio_risk(portfolio_id, signals, positions=positions)
            explanation = explain_portfolio_risk(portfolio_id, aggregates=aggregates, positions=positions)
    return render(
        request,
        "sourceflow/portfolio.html",
        {"portfolios": portfolios, "portfolio_id": portfolio_id, "explanation": explanation},
    )
