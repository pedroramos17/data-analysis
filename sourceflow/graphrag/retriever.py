"""Hybrid GraphRAG retriever over chunks, KG, claims, and events."""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from decimal import Decimal
from typing import Iterable

from sourceflow.graphrag.evidence_pack import (
    ConfidenceBreakdown,
    EvidenceItem,
    EvidencePack,
    average_decimal,
)
from sourceflow.kg import default_graph_store, node_ref
from sourceflow.retrieval.bm25 import RetrievalHit, search_chunks_bm25, tokenize
from sourceflow.retrieval.vector import search_chunks_vector

_CONFIDENCE_QUANTUM = Decimal("0.01")


@dataclass(frozen=True)
class ParsedQuery:
    """Query parse result used by the hybrid retriever."""

    raw: str
    tokens: tuple[str, ...]
    entities: tuple[object, ...]


class HybridGraphRAGRetriever:
    """Local-first hybrid retrieval with lexical, vector, and graph expansion."""

    name = "sourceflow_hybrid_graphrag"


    def __init__(self, *, graph_store: object | None = None) -> None:
        self.graph_store = graph_store or default_graph_store()

    def parse_query(self, query: str) -> ParsedQuery:
        """Parse query and detect known canonical entities."""
        from sourceflow.models import Entity, EntityAlias

        tokens = tuple(tokenize(query))
        lowered = query.lower()
        entities: list[object] = []
        seen: set[int] = set()
        for entity in Entity.objects.all():
            name = entity.canonical_name.lower()
            name_tokens = tokenize(name)
            if name and (name in lowered or all(token in tokens for token in name_tokens)):
                entities.append(entity)
                seen.add(entity.pk)
        aliases = EntityAlias.objects.select_related("entity").all()
        for alias in aliases:
            alias_text = alias.alias.lower()
            if alias.entity_id not in seen and alias_text and alias_text in lowered:
                entities.append(alias.entity)
                seen.add(alias.entity_id)
        return ParsedQuery(raw=query, tokens=tokens, entities=tuple(entities))

    def retrieve(self, query: str, *, limit: int = 10, persist_trace: bool = True) -> EvidencePack:
        """Return a provenance-carrying hybrid evidence pack."""
        from sourceflow.models import Claim, DocumentChunk, Event

        parsed = self.parse_query(query)
        chunks = list(DocumentChunk.objects.select_related("document", "document__source").all())
        bm25_hits = search_chunks_bm25(query, chunks, limit=limit)
        vector_hits = search_chunks_vector(query, chunks, limit=limit)
        chunk_hits = _merge_hits([*bm25_hits, *vector_hits], limit=limit)
        chunk_document_ids = {hit.provenance.get("document_id") for hit in chunk_hits if hit.provenance.get("document_id")}
        entity_ids = {entity.pk for entity in parsed.entities}

        supporting_claims = list(
            Claim.objects.select_related("source", "document", "evidence_span", "subject_entity", "object_entity").filter(
                _claim_filter_kwargs(entity_ids, chunk_document_ids)
            )[:limit]
        )
        events = list(
            Event.objects.select_related("source", "document", "evidence_span", "actor_entity", "object_entity").filter(
                _event_filter_kwargs(entity_ids, chunk_document_ids)
            )[:limit]
        )
        graph_edges = self._expand_graph(parsed.entities, supporting_claims, events, limit=limit)
        contradicting_claims = self._contradicting_claims(supporting_claims, limit=limit)

        pack = EvidencePack(
            query=query,
            text_chunks=tuple(_chunk_item(hit) for hit in chunk_hits),
            supporting_claims=tuple(_claim_item(claim, kind="supporting_claim") for claim in supporting_claims),
            contradicting_claims=tuple(_claim_item(claim, kind="contradicting_claim") for claim in contradicting_claims),
            events=tuple(_event_item(event) for event in events),
            entities=tuple(_entity_item(entity) for entity in parsed.entities),
            graph_paths=tuple(_edge_item(edge) for edge in graph_edges),
            assumptions_used=("OWA", "PartialCWA"),
            citations=tuple(_citations(chunk_hits, supporting_claims, contradicting_claims, events)),
            confidence=_confidence(chunk_hits, supporting_claims, contradicting_claims, events),
        )
        if persist_trace:
            self._persist_trace(pack)
        return pack

    def answer_query(self, query: str, answer: str, *, limit: int = 10) -> dict[str, object]:
        """Retrieve evidence and return a proof-carrying answer."""
        return self.retrieve(query, limit=limit).to_answer(answer)

    def _expand_graph(
        self,
        entities: Iterable[object],
        claims: Iterable[object],
        events: Iterable[object],
        *,
        limit: int,
    ) -> list[object]:
        edges: list[object] = []
        seen: set[int] = set()
        nodes = [node_ref("entity", entity.pk) for entity in entities]
        nodes.extend(node_ref("claim", claim.pk) for claim in claims)
        nodes.extend(node_ref("event", event.pk) for event in events)
        for node in nodes:
            for neighbor in self.graph_store.get_neighbors(node, direction="both"):
                edge_id = getattr(neighbor.edge, "pk", None)
                if edge_id in seen:
                    continue
                seen.add(edge_id)
                edges.append(neighbor.edge)
                if len(edges) >= limit:
                    return edges
        return edges

    def _contradicting_claims(self, claims: Iterable[object], *, limit: int) -> list[object]:
        from sourceflow.models import Claim, KnowledgeEdge

        claim_ids = [str(claim.pk) for claim in claims]
        if not claim_ids:
            return []
        target_ids = set(
            KnowledgeEdge.objects.filter(
                edge_type="contradicts",
                source_node_type="claim",
                source_node_id__in=claim_ids,
                target_node_type="claim",
            ).values_list("target_node_id", flat=True)
        )
        if not target_ids:
            return []
        return list(
            Claim.objects.select_related("source", "document", "evidence_span", "subject_entity", "object_entity").filter(
                pk__in=[int(target_id) for target_id in target_ids]
            )[:limit]
        )

    def _persist_trace(self, pack: EvidencePack) -> None:
        from sourceflow.models import RetrievalTrace

        payload = pack.to_dict()
        RetrievalTrace.objects.create(
            query=pack.query,
            query_hash=hashlib.sha256(pack.query.encode("utf-8")).hexdigest(),
            retriever_name=self.name,
            retrieval_mode="bm25+vector+kg",
            results_json=payload,
            citations_json=list(payload["citations"]),
            assumptions_json=list(pack.assumptions_used),
            retrieval_confidence=pack.confidence.retrieval_confidence,
            extraction_confidence=pack.confidence.extraction_confidence,
            reasoning_confidence=pack.confidence.reasoning_confidence,
            provenance_json={"created_by": "sourceflow.graphrag.retriever"},
        )


def hybrid_retrieve(query: str, *, limit: int = 10, persist_trace: bool = True) -> EvidencePack:
    """Convenience wrapper for hybrid GraphRAG retrieval."""
    return HybridGraphRAGRetriever().retrieve(query, limit=limit, persist_trace=persist_trace)


def _merge_hits(hits: list[RetrievalHit], *, limit: int) -> list[RetrievalHit]:
    merged: dict[str, RetrievalHit] = {}
    retrievers: dict[str, set[str]] = {}
    for hit in hits:
        if hit.identifier not in merged or hit.score > merged[hit.identifier].score:
            merged[hit.identifier] = hit
        retrievers.setdefault(hit.identifier, set()).add(hit.retriever)
    output: list[RetrievalHit] = []
    for identifier, hit in merged.items():
        provenance = {**dict(hit.provenance), "retrievers": sorted(retrievers[identifier])}
        output.append(
            RetrievalHit(
                identifier=identifier,
                score=hit.score,
                text=hit.text,
                payload=hit.payload,
                provenance=provenance,
                retriever="hybrid_chunk",
            )
        )
    return sorted(output, key=lambda item: item.score, reverse=True)[:limit]


def _claim_filter_kwargs(entity_ids: set[int], document_ids: set[object]):
    from django.db.models import Q

    query = Q()
    if entity_ids:
        query |= Q(subject_entity_id__in=entity_ids) | Q(object_entity_id__in=entity_ids)
    if document_ids:
        query |= Q(document_id__in=document_ids)
    return query if query else Q(pk__in=[])


def _event_filter_kwargs(entity_ids: set[int], document_ids: set[object]):
    from django.db.models import Q

    query = Q()
    if entity_ids:
        query |= Q(actor_entity_id__in=entity_ids) | Q(object_entity_id__in=entity_ids)
    if document_ids:
        query |= Q(document_id__in=document_ids)
    return query if query else Q(pk__in=[])


def _chunk_item(hit: RetrievalHit) -> EvidenceItem:
    return EvidenceItem(
        kind="text_chunk",
        identifier=hit.identifier,
        text=hit.text,
        score=_score(hit.score),
        provenance=hit.provenance,
        metadata={"retriever": hit.retriever},
    )


def _claim_item(claim: object, *, kind: str) -> EvidenceItem:
    return EvidenceItem(
        kind=kind,
        identifier=str(claim.pk),
        text=f"{claim.subject_entity} {claim.predicate} {claim.object_literal}".strip(),
        score=Decimal(str(claim.confidence)).quantize(_CONFIDENCE_QUANTUM),
        provenance={
            "claim_id": claim.pk,
            "source_id": claim.source_id,
            "source_name": claim.source.name,
            "document_id": claim.document_id,
            "evidence_span_id": claim.evidence_span_id,
            "evidence_text": claim.evidence_span.text,
        },
        metadata={"polarity": claim.polarity, "status": claim.status, "modality": claim.modality},
    )


def _event_item(event: object) -> EvidenceItem:
    return EvidenceItem(
        kind="event",
        identifier=str(event.pk),
        text=f"{event.actor_entity} {event.predicate} {event.object_literal}".strip(),
        score=Decimal(str(event.confidence)).quantize(_CONFIDENCE_QUANTUM),
        provenance={
            "event_id": event.pk,
            "source_id": event.source_id,
            "source_name": event.source.name,
            "document_id": event.document_id,
            "evidence_span_id": event.evidence_span_id,
            "evidence_text": event.evidence_span.text,
        },
        metadata={"event_type": event.event_type, "polarity": event.polarity},
    )


def _entity_item(entity: object) -> EvidenceItem:
    return EvidenceItem(
        kind="entity",
        identifier=str(entity.pk),
        text=entity.canonical_name,
        score=Decimal(str(entity.confidence)).quantize(_CONFIDENCE_QUANTUM),
        provenance={"entity_id": entity.pk, "entity_type": entity.entity_type},
        metadata={"country": entity.country, "sector": entity.sector},
    )


def _edge_item(edge: object) -> EvidenceItem:
    text = f"{edge.source_node_type}:{edge.source_node_id} -{edge.edge_type}-> {edge.target_node_type}:{edge.target_node_id}"
    return EvidenceItem(
        kind="graph_path",
        identifier=str(edge.pk),
        text=text,
        score=Decimal(str(edge.confidence)).quantize(_CONFIDENCE_QUANTUM),
        provenance={
            "edge_id": edge.pk,
            "source_document_id": edge.source_document_id,
            "evidence_span_id": edge.evidence_span_id,
            **dict(edge.provenance_json or {}),
        },
        metadata={"edge_type": edge.edge_type},
    )


def _citations(
    chunk_hits: list[RetrievalHit],
    supporting_claims: list[object],
    contradicting_claims: list[object],
    events: list[object],
) -> list[dict[str, object]]:
    citations: list[dict[str, object]] = []
    for hit in chunk_hits:
        citations.append({"kind": "text_chunk", **dict(hit.provenance)})
    for claim in [*supporting_claims, *contradicting_claims]:
        citations.append({"kind": "claim", "id": claim.pk, "source_id": claim.source_id, "document_id": claim.document_id, "evidence_span_id": claim.evidence_span_id})
    for event in events:
        citations.append({"kind": "event", "id": event.pk, "source_id": event.source_id, "document_id": event.document_id, "evidence_span_id": event.evidence_span_id})
    return citations


def _confidence(
    chunk_hits: list[RetrievalHit],
    supporting_claims: list[object],
    contradicting_claims: list[object],
    events: list[object],
) -> ConfidenceBreakdown:
    retrieval_scores = [_score(hit.score) for hit in chunk_hits]
    extraction_scores = [Decimal(str(record.confidence)).quantize(_CONFIDENCE_QUANTUM) for record in [*supporting_claims, *contradicting_claims, *events]]
    reasoning = Decimal("0.65") if contradicting_claims else Decimal("0.85") if supporting_claims or events else Decimal("0.40")
    return ConfidenceBreakdown(
        retrieval_confidence=average_decimal(retrieval_scores),
        extraction_confidence=average_decimal(extraction_scores),
        reasoning_confidence=reasoning,
    )


def _score(value: float) -> Decimal:
    return min(Decimal("1"), Decimal(str(max(value, 0.0)))).quantize(_CONFIDENCE_QUANTUM)
