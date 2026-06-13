"""Evidence-span helpers for provenance-first extraction."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal


@dataclass(frozen=True)
class EvidenceSpanSpec:
    """Text span with character offsets and extractor metadata."""

    text: str
    char_start: int
    char_end: int
    extractor_name: str
    extractor_version: str
    confidence: Decimal


def extract_evidence_span(
    source_text: str,
    evidence_text: str,
    *,
    extractor_name: str = "manual",
    extractor_version: str = "",
    confidence: Decimal | float | str = Decimal("1"),
    start_hint: int | None = None,
) -> EvidenceSpanSpec:
    """Locate exact evidence text inside source text."""
    if not evidence_text:
        raise ValueError("evidence_text must be non-empty")
    start = _find_text(source_text, evidence_text, start_hint)
    if start < 0:
        raise ValueError("evidence_text was not found in source_text")
    return EvidenceSpanSpec(
        text=evidence_text,
        char_start=start,
        char_end=start + len(evidence_text),
        extractor_name=extractor_name,
        extractor_version=extractor_version,
        confidence=Decimal(str(confidence)),
    )


def create_evidence_span_for_document(
    document: object,
    evidence_text: str,
    *,
    extractor_name: str = "manual",
    extractor_version: str = "",
    confidence: Decimal | float | str = Decimal("1"),
    start_hint: int | None = None,
) -> object:
    """Persist an evidence span for a canonical document."""
    from sourceflow.models import EvidenceSpan

    source_text = getattr(document, "clean_text", "") or getattr(document, "raw_text", "")
    spec = extract_evidence_span(
        source_text,
        evidence_text,
        extractor_name=extractor_name,
        extractor_version=extractor_version,
        confidence=confidence,
        start_hint=start_hint,
    )
    chunk = _chunk_for_document_span(document, spec.char_start, spec.char_end)
    return EvidenceSpan.objects.create(
        source_id=getattr(document, "source_id"),
        document=document,
        chunk=chunk,
        text=spec.text,
        char_start=spec.char_start,
        char_end=spec.char_end,
        extractor_name=spec.extractor_name,
        extractor_version=spec.extractor_version,
        confidence=spec.confidence,
        provenance_json={"created_by": "sourceflow.ingestion.evidence"},
    )


def evidence_for_claim(claim_id: int) -> dict[str, object]:
    """Return original document/chunk/span provenance for a claim."""
    from sourceflow.models import Claim

    claim = Claim.objects.select_related("source", "document", "evidence_span", "evidence_span__chunk").get(pk=claim_id)
    return _claim_payload(claim)


def evidence_for_belief(belief_id: int) -> dict[str, list[dict[str, object]]]:
    """Return supporting and contradicting claims for a belief."""
    from sourceflow.models import Justification

    rows = Justification.objects.select_related(
        "supporting_claim",
        "supporting_claim__source",
        "supporting_claim__document",
        "supporting_claim__evidence_span",
        "supporting_claim__evidence_span__chunk",
    ).filter(belief_id=belief_id, supporting_claim__isnull=False)
    supporting: list[dict[str, object]] = []
    contradicting: list[dict[str, object]] = []
    for row in rows:
        payload = _claim_payload(row.supporting_claim)
        if row.support_type == "contradicts":
            contradicting.append(payload)
        else:
            supporting.append(payload)
    return {"supporting_claims": supporting, "contradicting_claims": contradicting}


def _find_text(source_text: str, evidence_text: str, start_hint: int | None) -> int:
    if start_hint is not None:
        hinted = source_text.find(evidence_text, max(start_hint, 0))
        if hinted >= 0:
            return hinted
    return source_text.find(evidence_text)


def _chunk_for_document_span(document: object, char_start: int, char_end: int) -> object | None:
    chunks = getattr(document, "chunks")
    for chunk in chunks.order_by("chunk_index"):
        if chunk.char_start <= char_start and char_end <= chunk.char_end:
            return chunk
    for chunk in chunks.order_by("chunk_index"):
        if chunk.char_start <= char_start < chunk.char_end:
            return chunk
    return None


def _claim_payload(claim: object) -> dict[str, object]:
    evidence = claim.evidence_span
    chunk = evidence.chunk if evidence else None
    document = claim.document
    source = claim.source
    return {
        "claim_id": claim.pk,
        "source": {"id": source.pk, "name": source.name, "url": source.url},
        "document": {
            "id": document.pk,
            "url": document.url,
            "title": document.title,
            "content_hash": document.content_hash,
        },
        "chunk": {
            "id": chunk.pk,
            "chunk_index": chunk.chunk_index,
            "char_start": chunk.char_start,
            "char_end": chunk.char_end,
            "text": chunk.text,
        }
        if chunk
        else None,
        "evidence_span": {
            "id": evidence.pk,
            "text": evidence.text,
            "char_start": evidence.char_start,
            "char_end": evidence.char_end,
            "extractor_name": evidence.extractor_name,
            "extractor_version": evidence.extractor_version,
            "confidence": float(evidence.confidence),
        }
        if evidence
        else None,
    }
