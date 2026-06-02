"""Retrieval-first paper question answering."""

from __future__ import annotations

from django.conf import settings

from quantspace.services.evidence import (
    chunk_evidence_payload,
    create_question_citation,
)
from quantspace.services.vector_search import search_paper_chunks
from sourceflow.config.feature_flags import feature_flag_enabled, require_feature


def answer_paper_question(
    paper: object,
    question: str,
    limit: int = 5,
) -> dict[str, object]:
    """Answer from retrieved chunks, with prompt preview when no LLM exists.

    Example:
        `answer_paper_question(paper, "What data split is used?")`
    """
    require_feature("QUANTSPACE_CORE")
    results = search_paper_chunks(paper, question, limit=limit)
    prompt_preview = build_question_prompt(paper.title, question, results)
    provider = _configured_llm_provider()
    answer = _retrieval_answer(results, provider)
    record = _record_question(paper, question, answer, prompt_preview, provider)
    for result in results:
        create_question_citation(record, result.chunk)
    return _answer_payload(record, results)


def build_question_prompt(
    title: str,
    question: str,
    results: list[object],
) -> str:
    """Build the local prompt preview sent to a future LLM provider.

    Example:
        `build_question_prompt("Paper", "Question?", [])`
    """
    snippets = [result.chunk.text[:700] for result in results]
    context = "\n\n".join(snippets) or "No relevant chunks retrieved."
    return f"Paper: {title}\nQuestion: {question}\nContext:\n{context}"


def _configured_llm_provider() -> str:
    if not feature_flag_enabled("QUANTSPACE_LLM_PROVIDER"):
        return ""
    return str(getattr(settings, "QUANTSPACE_LLM_PROVIDER", "")).strip()


def _retrieval_answer(results: list[object], provider: str) -> str:
    if provider:
        return "LLM provider configured; local preview stored."
    if not results:
        return "No LLM provider configured and no relevant chunks were retrieved."
    return "No LLM provider configured; review the retrieved chunks below."


def _record_question(
    paper: object,
    question: str,
    answer: str,
    prompt_preview: str,
    provider: str,
) -> object:
    from quantspace.models import PaperQuestion

    status = "LLM_READY" if provider else "RETRIEVAL_ONLY"
    return PaperQuestion.objects.create(
        paper=paper,
        question=question,
        answer=answer,
        prompt_preview=prompt_preview,
        llm_provider=provider,
        status=status,
    )


def _answer_payload(record: object, results: list[object]) -> dict[str, object]:
    return {
        "question_id": record.id,
        "answer": record.answer,
        "prompt_preview": record.prompt_preview,
        "retrieved_chunks": [
            chunk_evidence_payload(result.chunk) for result in results
        ],
    }
