"""Citation helpers for retrieved paper evidence."""

from __future__ import annotations

from quantspace.services.status import normalize_support_status


def chunk_evidence_payload(chunk: object) -> dict[str, object]:
    """Return a serializable citation payload for one chunk.

    Example:
        `chunk_evidence_payload(chunk)["page_start"]`
    """
    return {
        "chunk_id": chunk.id,
        "page_start": chunk.page_start,
        "page_end": chunk.page_end,
        "text": chunk.text,
        "support_status": normalize_support_status(chunk.support_status),
    }


def create_question_citation(question: object, chunk: object) -> object:
    """Persist a citation for a retrieval-only answer.

    Example:
        `create_question_citation(question, chunk)`
    """
    from quantspace.models import PaperCitation

    return PaperCitation.objects.create(
        paper=question.paper,
        question=question,
        chunk=chunk,
        page_start=chunk.page_start,
        page_end=chunk.page_end,
        quote=chunk.text[:500],
        support_status=normalize_support_status(chunk.support_status),
    )
