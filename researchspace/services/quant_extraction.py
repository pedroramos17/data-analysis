"""Quant methodology extraction from local paper chunks."""

from __future__ import annotations

from researchspace.services.quant_schema import (
    extraction_prompt_preview,
    parse_quant_extraction_payload,
)
from researchspace.services.status import normalize_support_status
from sourceflow.config.feature_flags import require_feature


def extract_quant_methodology(
    paper: object,
    raw_response: str = "",
) -> object:
    """Create a structured extraction record from local chunks or model text.

    Example:
        `extract_quant_methodology(paper)`
    """
    require_feature("RESEARCHSPACE_QUANT_EXTRACTION")
    context = _paper_context(paper)
    prompt_preview = extraction_prompt_preview(paper.title, context)
    source_text = raw_response or _local_partial_json(context)
    extraction_json = parse_quant_extraction_payload(source_text)
    return _create_extraction(paper, extraction_json, source_text, prompt_preview)


def _paper_context(paper: object) -> str:
    chunks = paper.chunks.all()[:8]
    return "\n\n".join(chunk.text[:900] for chunk in chunks)


def _local_partial_json(context: str) -> str:
    support = "PARTIAL" if context else "NEEDS_REVIEW"
    return (
        '{"methodology": [], "datasets": [], "models": [], '
        f'"validation": [], "factors": [], "support_status": "{support}"}}'
    )


def _create_extraction(
    paper: object,
    extraction_json: dict[str, object],
    raw_response: str,
    prompt_preview: str,
) -> object:
    from researchspace.models import QuantExtraction

    return QuantExtraction.objects.create(
        paper=paper,
        extraction_json=extraction_json,
        raw_response=raw_response,
        prompt_preview=prompt_preview,
        support_status=normalize_support_status(extraction_json.get("support_status")),
        status="EXTRACTED",
    )
