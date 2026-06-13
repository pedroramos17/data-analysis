"""Phase 11 HTTP endpoints over the canonical sourceflow knowledge layer.

These are plain Django function views (the project does not use DRF) wrapped by
:func:`sourceflow.api.responses.api_endpoint`, which enforces the HTTP method,
renders JSON, logs the call, and maps known failures to typed error envelopes.

Read endpoints (documents/entities/claims/events/kg/beliefs) are backed by
Phases 0-6. The reasoning, source-comparison, GraphRAG, and quant endpoints are
backed by the Phase 7-10 modules. Heavy phase modules are imported lazily inside
each view so a missing optional dependency can never break the whole URLconf.
"""

from __future__ import annotations

import dataclasses
from pathlib import Path
from typing import Any

from django.conf import settings
from django.http import HttpRequest

from sourceflow.api.responses import ApiError, api_endpoint, parse_json_body
from sourceflow.api.serializers import (
    serialize_belief,
    serialize_claim,
    serialize_document,
    serialize_entity,
    serialize_event,
    serialize_justification,
)


# --------------------------------------------------------------------------- #
# helpers
# --------------------------------------------------------------------------- #

def _limit_offset(request: HttpRequest, *, default: int = 50, maximum: int = 500) -> tuple[int, int]:
    try:
        limit = int(request.GET.get("limit", default))
        offset = int(request.GET.get("offset", 0))
    except ValueError as exc:
        raise ApiError("limit and offset must be integers", status=400, error_type="bad_request") from exc
    return max(0, min(limit, maximum)), max(0, offset)


def _asdict(obj: Any) -> Any:
    """Recursively convert dataclass results to JSON-able dicts."""
    if dataclasses.is_dataclass(obj) and not isinstance(obj, type):
        return {key: _asdict(value) for key, value in dataclasses.asdict(obj).items()}
    if isinstance(obj, (list, tuple)):
        return [_asdict(item) for item in obj]
    if isinstance(obj, dict):
        return {str(key): _asdict(value) for key, value in obj.items()}
    return obj


def _rules_dir() -> Path:
    base = getattr(settings, "BASE_DIR", None)
    if base:
        candidate = Path(base) / "rules"
        if candidate.exists():
            return candidate
    return Path(__file__).resolve().parents[2] / "rules"


# --------------------------------------------------------------------------- #
# Phase 0-4: records
# --------------------------------------------------------------------------- #

@api_endpoint(methods=("GET",))
def documents(request: HttpRequest) -> dict[str, Any]:
    from sourceflow.models import Document

    limit, offset = _limit_offset(request)
    queryset = Document.objects.select_related("source").all()
    total = queryset.count()
    rows = list(queryset[offset : offset + limit])
    return {"count": total, "limit": limit, "offset": offset, "results": [serialize_document(d) for d in rows]}


@api_endpoint(methods=("GET",))
def entities(request: HttpRequest) -> dict[str, Any]:
    from sourceflow.models import Entity

    limit, offset = _limit_offset(request)
    queryset = Entity.objects.all()
    entity_type = request.GET.get("entity_type")
    if entity_type:
        queryset = queryset.filter(entity_type=entity_type)
    query = request.GET.get("q")
    if query:
        queryset = queryset.filter(canonical_name__icontains=query)
    total = queryset.count()
    rows = list(queryset[offset : offset + limit])
    return {"count": total, "limit": limit, "offset": offset, "results": [serialize_entity(e) for e in rows]}


@api_endpoint(methods=("GET",))
def claims(request: HttpRequest) -> dict[str, Any]:
    from sourceflow.models import Claim

    limit, offset = _limit_offset(request)
    queryset = Claim.objects.select_related("subject_entity", "object_entity", "source", "document", "evidence_span").all()
    subject = request.GET.get("subject_entity_id")
    if subject:
        queryset = queryset.filter(subject_entity_id=subject)
    status = request.GET.get("status")
    if status:
        queryset = queryset.filter(status=status)
    total = queryset.count()
    rows = list(queryset[offset : offset + limit])
    return {"count": total, "limit": limit, "offset": offset, "results": [serialize_claim(c, with_evidence=True) for c in rows]}


@api_endpoint(methods=("GET",))
def events(request: HttpRequest) -> dict[str, Any]:
    from sourceflow.models import Event

    limit, offset = _limit_offset(request)
    queryset = Event.objects.select_related("actor_entity", "object_entity", "source", "document", "evidence_span").all()
    actor = request.GET.get("actor_entity_id")
    if actor:
        queryset = queryset.filter(actor_entity_id=actor)
    event_type = request.GET.get("event_type")
    if event_type:
        queryset = queryset.filter(event_type=event_type)
    total = queryset.count()
    rows = list(queryset[offset : offset + limit])
    return {"count": total, "limit": limit, "offset": offset, "results": [serialize_event(e, with_evidence=True) for e in rows]}


# --------------------------------------------------------------------------- #
# Phase 5: knowledge graph
# --------------------------------------------------------------------------- #

def _serialize_edge(edge: Any) -> dict[str, Any]:
    return {
        "edge_type": edge.edge_type,
        "source": {"type": edge.source_node_type, "id": edge.source_node_id},
        "target": {"type": edge.target_node_type, "id": edge.target_node_id},
        "confidence": float(edge.confidence),
        "observed_at": edge.observed_at.isoformat() if edge.observed_at else None,
        "provenance": dict(edge.provenance_json or {}),
    }


@api_endpoint(methods=("GET",))
def kg_entity(request: HttpRequest, entity_id: str) -> dict[str, Any]:
    from sourceflow.kg import GraphSchemaError, default_graph_store, node_ref
    from sourceflow.models import Entity

    try:
        node = node_ref("entity", entity_id)
    except GraphSchemaError as exc:
        raise ApiError(str(exc), status=400, error_type="bad_request") from exc

    entity = Entity.objects.filter(pk=entity_id).first()
    direction = request.GET.get("direction", "both")
    if direction not in {"out", "in", "both"}:
        raise ApiError("direction must be one of out/in/both", status=400, error_type="bad_request")
    edge_type = request.GET.get("edge_type") or None

    store = default_graph_store()
    try:
        neighbors = store.get_neighbors(node, edge_type=edge_type, direction=direction)
    except GraphSchemaError as exc:
        raise ApiError(str(exc), status=400, error_type="bad_request") from exc

    return {
        "entity": serialize_entity(entity) if entity else {"id": entity_id, "note": "no canonical entity row"},
        "node": {"type": node.node_type, "id": node.node_id},
        "direction": direction,
        "neighbors": [
            {"node": {"type": n.node.node_type, "id": n.node.node_id}, "edge": _serialize_edge(n.edge)}
            for n in neighbors
        ],
    }


@api_endpoint(methods=("GET",))
def kg_path(request: HttpRequest) -> dict[str, Any]:
    from sourceflow.kg import GraphSchemaError, default_graph_store, node_ref

    required = ("source_type", "source_id", "target_type", "target_id")
    missing = [field for field in required if not request.GET.get(field)]
    if missing:
        raise ApiError(
            f"missing required query params: {', '.join(missing)}",
            status=400,
            error_type="bad_request",
        )
    try:
        max_depth = int(request.GET.get("max_depth", 3))
    except ValueError as exc:
        raise ApiError("max_depth must be an integer", status=400, error_type="bad_request") from exc
    if not 1 <= max_depth <= 6:
        raise ApiError("max_depth must be between 1 and 6", status=400, error_type="bad_request")

    try:
        start = node_ref(request.GET["source_type"], request.GET["source_id"])
        end = node_ref(request.GET["target_type"], request.GET["target_id"])
    except GraphSchemaError as exc:
        raise ApiError(str(exc), status=400, error_type="bad_request") from exc

    paths = default_graph_store().find_paths(start, end, max_depth=max_depth)
    return {
        "start": {"type": start.node_type, "id": start.node_id},
        "end": {"type": end.node_type, "id": end.node_id},
        "max_depth": max_depth,
        "path_count": len(paths),
        "paths": [[_serialize_edge(edge) for edge in path] for path in paths],
    }


# --------------------------------------------------------------------------- #
# Phase 6: belief explanation
# --------------------------------------------------------------------------- #

@api_endpoint(methods=("GET",))
def belief_explain(request: HttpRequest, belief_id: int) -> dict[str, Any]:
    from sourceflow.models import Belief
    from sourceflow.tms import CONTRADICTING_TYPES, justification_is_active, recompute_belief

    belief = (
        Belief.objects.select_related("assumption_policy", "created_by_rule", "subject_entity", "object_entity")
        .filter(pk=belief_id)
        .first()
    )
    if belief is None:
        raise ApiError(f"belief {belief_id} not found", status=404, error_type="not_found")

    # Recompute so the explanation reflects the current state of its support.
    resolution = recompute_belief(belief)

    supporting: list[dict[str, Any]] = []
    contradicting: list[dict[str, Any]] = []
    for justification in belief.justifications.select_related(
        "supporting_claim", "supporting_event", "supporting_belief", "rule"
    ).all():
        entry = serialize_justification(justification)
        entry["active"] = justification_is_active(justification)
        if justification.support_type in CONTRADICTING_TYPES:
            contradicting.append(entry)
        else:
            supporting.append(entry)

    return {
        "belief": serialize_belief(belief),
        "explanation": {
            "truth_status": resolution.truth_status,
            "confidence": float(resolution.confidence),
            "assumption_policy": getattr(belief.assumption_policy, "code", None),
            "why": getattr(resolution, "explanation", ""),
        },
        "supporting_justifications": supporting,
        "contradicting_justifications": contradicting,
        "provenance": dict(belief.provenance_json or {}),
    }


# --------------------------------------------------------------------------- #
# Phase 7: reasoning
# --------------------------------------------------------------------------- #

@api_endpoint(methods=("POST",))
def reasoning_run(request: HttpRequest) -> dict[str, Any]:
    body = parse_json_body(request)
    mode = str(body.get("mode", "infer")).lower()

    if mode == "infer":
        return _reasoning_infer(body)
    if mode == "diagnose":
        return _reasoning_diagnose(body)
    raise ApiError(f"unknown reasoning mode: {mode!r}; expected 'infer' or 'diagnose'", status=400, error_type="bad_request")


def _reasoning_infer(body: dict[str, Any]) -> dict[str, Any]:
    from sourceflow.models import Event
    from sourceflow.reasoning import InferenceEngine

    queryset = Event.objects.all()
    event_ids = body.get("event_ids")
    if isinstance(event_ids, list) and event_ids:
        queryset = queryset.filter(pk__in=event_ids)
    limit = int(body.get("limit", 50))
    target_events = list(queryset[: max(1, min(limit, 200))])

    engine = InferenceEngine.from_default_rules(_rules_dir())
    engine.upsert_rules()
    results = engine.infer_from_events(target_events)

    serialized = []
    for result in results:
        serialized.append(
            {
                "rule_id": result.rule_id,
                "status": result.status,
                "reason": result.reason,
                "belief": serialize_belief(result.belief) if result.belief is not None else None,
                "support": {
                    "kind": result.support.__class__.__name__.lower() if result.support is not None else None,
                    "id": getattr(result.support, "pk", None),
                },
            }
        )
    created = [item for item in serialized if item["status"] == "created"]
    return {
        "mode": "infer",
        "events_considered": len(target_events),
        "rules_applied": len({item["rule_id"] for item in serialized}),
        "beliefs_created": len(created),
        "results": serialized,
    }


def _reasoning_diagnose(body: dict[str, Any]) -> dict[str, Any]:
    from sourceflow.models import Claim, Event, KnowledgeEdge
    from sourceflow.reasoning import diagnose_anomaly

    anomaly = body.get("anomaly")
    if not isinstance(anomaly, dict) or not anomaly.get("anomaly_type"):
        raise ApiError(
            "diagnose mode requires an 'anomaly' object with at least an 'anomaly_type'",
            status=422,
            error_type="unprocessable_entity",
        )
    limit = int(body.get("limit", 5))
    events = list(Event.objects.all()[:100])
    claims = list(Claim.objects.all()[:100])
    edges = list(KnowledgeEdge.objects.all()[:200])
    hypotheses = diagnose_anomaly(
        anomaly,
        events=events,
        claims=claims,
        graph_edges=edges,
        market_evidence=anomaly.get("market_evidence") or {},
        limit=max(1, min(limit, 20)),
    )
    return {
        "mode": "diagnose",
        "anomaly": anomaly,
        "hypothesis_count": len(hypotheses),
        "hypotheses": [_asdict(hypothesis) for hypothesis in hypotheses],
    }


# --------------------------------------------------------------------------- #
# Phase 8: source comparison
# --------------------------------------------------------------------------- #

@api_endpoint(methods=("GET",))
def source_comparison_event(request: HttpRequest, event_id: int) -> dict[str, Any]:
    from sourceflow.claims import compare_event_cluster_claims
    from sourceflow.events import cluster_events, event_cluster_key
    from sourceflow.models import Claim, Event, Source

    event = Event.objects.select_related("actor_entity").filter(pk=event_id).first()
    if event is None:
        raise ApiError(f"event {event_id} not found", status=404, error_type="not_found")

    target_key = event_cluster_key(event)
    sibling_events = list(
        Event.objects.select_related("source", "document", "actor_entity").filter(
            actor_entity_id=event.actor_entity_id, event_type=event.event_type
        )
    )
    related_claims = list(
        Claim.objects.select_related("source", "document", "subject_entity").filter(
            subject_entity_id=event.actor_entity_id
        )
    )
    clusters = cluster_events(sibling_events, claims=related_claims)
    cluster = next((c for c in clusters if c.key == target_key), clusters[0] if clusters else None)
    if cluster is None:
        raise ApiError("could not assemble an event cluster for comparison", status=422, error_type="unprocessable_entity")

    group_by = tuple(request.GET.get("group_by", "owner").split(",")) or ("owner",)
    comparison = compare_event_cluster_claims(
        cluster,
        claims=related_claims,
        expected_sources=list(Source.objects.all()),
        group_by=group_by,
    )
    return {
        "event_id": event_id,
        "cluster_id": comparison.cluster_id,
        "group_by": list(comparison.group_by),
        "assumption_policy": comparison.assumption_policy,
        "summaries": [_asdict(summary) for summary in comparison.summaries],
        "findings": [_asdict(finding) for finding in comparison.findings],
    }


# --------------------------------------------------------------------------- #
# Phase 9: GraphRAG
# --------------------------------------------------------------------------- #

@api_endpoint(methods=("POST",))
def graphrag_query(request: HttpRequest) -> dict[str, Any]:
    from sourceflow.graphrag import EvidencePackError, hybrid_retrieve

    body = parse_json_body(request)
    query = str(body.get("query", "")).strip()
    if not query:
        raise ApiError("a non-empty 'query' is required", status=422, error_type="unprocessable_entity")
    limit = int(body.get("limit", 10))
    pack = hybrid_retrieve(query, limit=max(1, min(limit, 50)))

    answer = body.get("answer")
    if answer:
        try:
            what_would_change = tuple(body.get("what_would_change_this", []) or ())
            return pack.to_answer(str(answer), what_would_change_this=what_would_change)
        except EvidencePackError as exc:
            raise ApiError(str(exc), status=422, error_type="no_evidence") from exc
    return pack.to_dict()


# --------------------------------------------------------------------------- #
# Phase 10: quant risk + portfolio explanation
# --------------------------------------------------------------------------- #

@api_endpoint(methods=("GET",))
def quant_risk(request: HttpRequest, asset_id: str) -> dict[str, Any]:
    from sourceflow.models import Entity, Event
    from sourceflow.quant import RiskGraph

    entity = Entity.objects.filter(pk=asset_id).first()
    events = list(
        Event.objects.select_related("actor_entity").filter(actor_entity_id=asset_id).order_by("-event_time")[:50]
    )
    risk_graph = RiskGraph()
    signals: list[Any] = []
    for event in events:
        direct = risk_graph.propagate_event_risk(event)
        signals.extend(direct)
        for base_signal in direct:
            signals.extend(risk_graph.propagate_supplier_customer_risk(base_signal))

    return {
        "asset_id": asset_id,
        "entity": serialize_entity(entity) if entity else None,
        "events_considered": len(events),
        "risk_signal_count": len(signals),
        "risk_signals": [_asdict(signal) for signal in signals],
    }


@api_endpoint(methods=("GET",))
def quant_portfolio_explain(request: HttpRequest) -> dict[str, Any]:
    from sourceflow.models import Event, PortfolioPosition
    from sourceflow.quant import RiskGraph, explain_portfolio_risk

    portfolio_id = request.GET.get("portfolio_id")
    if not portfolio_id:
        raise ApiError("query param 'portfolio_id' is required", status=400, error_type="bad_request")

    positions = list(
        PortfolioPosition.objects.select_related("asset", "instrument").filter(portfolio_id=portfolio_id)
    )
    if not positions:
        raise ApiError(f"no positions found for portfolio {portfolio_id!r}", status=404, error_type="not_found")

    risk_graph = RiskGraph()
    signals: list[Any] = []
    for event in Event.objects.select_related("actor_entity").order_by("-event_time")[:100]:
        direct = risk_graph.propagate_event_risk(event)
        signals.extend(direct)
        for base_signal in direct:
            signals.extend(risk_graph.propagate_supplier_customer_risk(base_signal))

    aggregates = risk_graph.aggregate_portfolio_risk(portfolio_id, signals, positions=positions)
    explanation = explain_portfolio_risk(portfolio_id, aggregates=aggregates, positions=positions)
    return {
        "portfolio_id": portfolio_id,
        "position_count": len(positions),
        "explanation": _asdict(explanation),
    }
