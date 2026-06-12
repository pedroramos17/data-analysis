"""Abductive diagnosis for market anomalies."""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Iterable, Mapping

_CONFIDENCE_QUANTUM = Decimal("0.01")


@dataclass(frozen=True)
class AnomalyInput:
    """Observed market anomaly to explain."""

    anomaly_type: str
    subject: str = ""
    direction: str = "unknown"
    magnitude: Decimal = Decimal("0")
    market_evidence: Mapping[str, object] = field(default_factory=dict)


@dataclass(frozen=True)
class EvidenceReference:
    """Compact reference to evidence supporting a hypothesis."""

    kind: str
    identifier: str
    summary: str
    confidence: Decimal = Decimal("0")


@dataclass(frozen=True)
class DiagnosisHypothesis:
    """Ranked abductive explanation for an anomaly."""

    hypothesis: str
    confidence: Decimal
    supporting_evidence: tuple[EvidenceReference, ...]
    missing_evidence: tuple[str, ...]
    graph_path: tuple[str, ...]
    recommended_next_retrieval: tuple[str, ...]


def diagnose_anomaly(
    anomaly: AnomalyInput | Mapping[str, object],
    *,
    events: Iterable[object] = (),
    claims: Iterable[object] = (),
    graph_edges: Iterable[object] = (),
    market_evidence: Mapping[str, object] | None = None,
    limit: int = 5,
) -> list[DiagnosisHypothesis]:
    """Generate ranked hypotheses for an observed anomaly."""
    normalized = _normalize_anomaly(anomaly, market_evidence=market_evidence)
    event_refs = [_event_reference(event) for event in events]
    claim_refs = [_claim_reference(claim) for claim in claims]
    graph_paths = tuple(_edge_path(edge) for edge in graph_edges)
    market_refs = _market_references(normalized.market_evidence)

    hypotheses = [
        _news_pressure_hypothesis(normalized, event_refs, claim_refs, graph_paths, market_refs),
        _risk_event_hypothesis(normalized, event_refs, claim_refs, graph_paths, market_refs),
        _liquidity_hypothesis(normalized, event_refs, claim_refs, graph_paths, market_refs),
        _macro_sector_hypothesis(normalized, event_refs, claim_refs, graph_paths, market_refs),
    ]
    ranked = sorted(hypotheses, key=lambda item: item.confidence, reverse=True)
    return ranked[:limit]


def diagnose_stock_move(
    *,
    subject_entity: object | None = None,
    symbol: str = "",
    price_move: Decimal | float | str = Decimal("0"),
    events: Iterable[object] | None = None,
    claims: Iterable[object] | None = None,
    graph_edges: Iterable[object] | None = None,
    market_evidence: Mapping[str, object] | None = None,
    limit: int = 5,
) -> list[DiagnosisHypothesis]:
    """Django-friendly helper for explaining a stock move."""
    from sourceflow.models import Claim, Event, KnowledgeEdge

    subject_name = getattr(subject_entity, "canonical_name", "") or symbol
    selected_events = list(events) if events is not None else list(Event.objects.filter(actor_entity=subject_entity)[:50])
    selected_claims = list(claims) if claims is not None else list(Claim.objects.filter(subject_entity=subject_entity)[:50])
    if graph_edges is not None:
        selected_edges = list(graph_edges)
    elif subject_entity is not None:
        selected_edges = list(
            KnowledgeEdge.objects.filter(target_node_type="entity", target_node_id=str(subject_entity.pk))[:50]
        )
    else:
        selected_edges = []
    anomaly = AnomalyInput(
        anomaly_type="price_move",
        subject=subject_name,
        direction="down" if Decimal(str(price_move)) < 0 else "up",
        magnitude=abs(Decimal(str(price_move))),
        market_evidence=market_evidence or {"price_move": str(price_move)},
    )
    return diagnose_anomaly(
        anomaly,
        events=selected_events,
        claims=selected_claims,
        graph_edges=selected_edges,
        limit=limit,
    )


def _news_pressure_hypothesis(
    anomaly: AnomalyInput,
    event_refs: list[EvidenceReference],
    claim_refs: list[EvidenceReference],
    graph_paths: tuple[str, ...],
    market_refs: tuple[EvidenceReference, ...],
) -> DiagnosisHypothesis:
    supporting = tuple(ref for ref in [*event_refs, *claim_refs, *market_refs] if _has_any(ref.summary, {"negative", "lawsuit", "regulatory", "credit", "downgrade"}))
    return _hypothesis(
        name=f"negative news pressure may explain {anomaly.subject or 'the asset'} {anomaly.anomaly_type}",
        base=Decimal("0.25"),
        supporting=supporting,
        graph_paths=graph_paths,
        missing=_missing(supporting, graph_paths, require_event=True, require_claim=True),
        retrieval=("retrieve recent negative news cluster", "retrieve source confirmations and denials"),
    )


def _risk_event_hypothesis(
    anomaly: AnomalyInput,
    event_refs: list[EvidenceReference],
    claim_refs: list[EvidenceReference],
    graph_paths: tuple[str, ...],
    market_refs: tuple[EvidenceReference, ...],
) -> DiagnosisHypothesis:
    supporting = tuple(ref for ref in [*event_refs, *claim_refs, *market_refs] if _has_any(ref.summary, {"lawsuit", "regulatory", "litigation", "investigation", "risk"}))
    return _hypothesis(
        name="event-driven risk repricing",
        base=Decimal("0.20"),
        supporting=supporting,
        graph_paths=graph_paths,
        missing=_missing(supporting, graph_paths, require_event=True, require_claim=False),
        retrieval=("retrieve legal/regulatory updates", "retrieve KG paths to risk factors"),
    )


def _liquidity_hypothesis(
    anomaly: AnomalyInput,
    event_refs: list[EvidenceReference],
    claim_refs: list[EvidenceReference],
    graph_paths: tuple[str, ...],
    market_refs: tuple[EvidenceReference, ...],
) -> DiagnosisHypothesis:
    supporting = tuple(ref for ref in market_refs if _has_any(ref.summary, {"volume", "volatility", "lob", "liquidity", "spread"}))
    return _hypothesis(
        name="liquidity or microstructure stress",
        base=Decimal("0.15"),
        supporting=supporting,
        graph_paths=graph_paths,
        missing=_missing(supporting, graph_paths, require_event=False, require_claim=False),
        retrieval=("retrieve LOB snapshots around anomaly", "retrieve intraday volume and spread panel"),
    )


def _macro_sector_hypothesis(
    anomaly: AnomalyInput,
    event_refs: list[EvidenceReference],
    claim_refs: list[EvidenceReference],
    graph_paths: tuple[str, ...],
    market_refs: tuple[EvidenceReference, ...],
) -> DiagnosisHypothesis:
    supporting = tuple(ref for ref in [*event_refs, *claim_refs, *market_refs] if _has_any(ref.summary, {"macro", "sector", "fed", "rates", "divergence"}))
    return _hypothesis(
        name="macro or sector divergence",
        base=Decimal("0.10"),
        supporting=supporting,
        graph_paths=graph_paths,
        missing=_missing(supporting, graph_paths, require_event=False, require_claim=False),
        retrieval=("retrieve macro calendar", "retrieve peer and sector move comparison"),
    )


def _hypothesis(
    *,
    name: str,
    base: Decimal,
    supporting: tuple[EvidenceReference, ...],
    graph_paths: tuple[str, ...],
    missing: tuple[str, ...],
    retrieval: tuple[str, ...],
) -> DiagnosisHypothesis:
    confidence = min(Decimal("1"), base + Decimal("0.15") * len(supporting) + Decimal("0.10") * bool(graph_paths))
    return DiagnosisHypothesis(
        hypothesis=name,
        confidence=confidence.quantize(_CONFIDENCE_QUANTUM),
        supporting_evidence=supporting,
        missing_evidence=missing,
        graph_path=graph_paths,
        recommended_next_retrieval=retrieval,
    )


def _missing(
    supporting: tuple[EvidenceReference, ...],
    graph_paths: tuple[str, ...],
    *,
    require_event: bool,
    require_claim: bool,
) -> tuple[str, ...]:
    missing: list[str] = []
    if require_event and not any(ref.kind == "event" for ref in supporting):
        missing.append("market-moving event evidence")
    if require_claim and not any(ref.kind == "claim" for ref in supporting):
        missing.append("source claim confirmation")
    if not graph_paths:
        missing.append("knowledge graph path to asset or risk factor")
    if not any(ref.kind == "market" for ref in supporting):
        missing.append("market microstructure confirmation")
    return tuple(missing)


def _normalize_anomaly(anomaly: AnomalyInput | Mapping[str, object], *, market_evidence: Mapping[str, object] | None) -> AnomalyInput:
    if isinstance(anomaly, AnomalyInput):
        if market_evidence is None:
            return anomaly
        return AnomalyInput(
            anomaly_type=anomaly.anomaly_type,
            subject=anomaly.subject,
            direction=anomaly.direction,
            magnitude=anomaly.magnitude,
            market_evidence={**dict(anomaly.market_evidence), **dict(market_evidence)},
        )
    return AnomalyInput(
        anomaly_type=str(anomaly.get("anomaly_type") or anomaly.get("type") or "anomaly"),
        subject=str(anomaly.get("subject") or anomaly.get("symbol") or ""),
        direction=str(anomaly.get("direction") or "unknown"),
        magnitude=Decimal(str(anomaly.get("magnitude") or 0)),
        market_evidence={**dict(anomaly.get("market_evidence") or {}), **dict(market_evidence or {})},
    )


def _event_reference(event: object) -> EvidenceReference:
    return EvidenceReference(
        kind="event",
        identifier=str(_value(event, "pk") or _value(event, "id")),
        summary=" ".join(
            str(part)
            for part in (
                _value(event, "event_type"),
                _value(event, "polarity"),
                _value(event, "predicate"),
                _value(event, "object_literal"),
            )
            if part
        ),
        confidence=Decimal(str(_value(event, "confidence") or 0)),
    )


def _claim_reference(claim: object) -> EvidenceReference:
    return EvidenceReference(
        kind="claim",
        identifier=str(_value(claim, "pk") or _value(claim, "id")),
        summary=" ".join(
            str(part)
            for part in (
                _value(claim, "polarity"),
                _value(claim, "predicate"),
                _value(claim, "object_literal"),
                _value(claim, "status"),
            )
            if part
        ),
        confidence=Decimal(str(_value(claim, "confidence") or 0)),
    )


def _edge_path(edge: object) -> str:
    if isinstance(edge, str):
        return edge
    return f"{_value(edge, 'source_node_type')}:{_value(edge, 'source_node_id')} -{_value(edge, 'edge_type')}-> {_value(edge, 'target_node_type')}:{_value(edge, 'target_node_id')}"


def _market_references(market_evidence: Mapping[str, object]) -> tuple[EvidenceReference, ...]:
    refs: list[EvidenceReference] = []
    for key, value in market_evidence.items():
        refs.append(EvidenceReference("market", str(key), f"{key}: {value}", Decimal("0.70")))
    return tuple(refs)


def _has_any(value: str, terms: set[str]) -> bool:
    lowered = value.lower()
    return any(term in lowered for term in terms)


def _value(record: object, key: str) -> object:
    return record.get(key, "") if isinstance(record, Mapping) else getattr(record, key, "")
