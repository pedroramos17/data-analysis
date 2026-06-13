"""Generate Sourceflow factor candidates from ResearchSpace extractions."""

from __future__ import annotations

from researchspace.services.prompt_export import build_codex_prompt
from researchspace.services.status import normalize_support_status
from sourceflow.config.feature_flags import require_feature


def generate_factor_candidates(extraction: object) -> list[object]:
    """Create NEEDS_BACKTEST candidates from extraction JSON factors.

    Example:
        `generate_factor_candidates(extraction)`
    """
    require_feature("RESEARCHSPACE_FACTOR_LAB")
    factor_payloads = extraction.extraction_json.get("factors", [])
    candidates = [_create_candidate(extraction, item) for item in factor_payloads]
    if candidates:
        return candidates
    return [_create_candidate(extraction, _fallback_factor(extraction))]


def _create_candidate(extraction: object, payload: object) -> object:
    from researchspace.models import FactorCandidate

    factor_payload = payload if isinstance(payload, dict) else {}
    candidate = FactorCandidate.objects.create(
        paper=extraction.paper,
        extraction=extraction,
        name=str(factor_payload.get("name") or "PaperEvidenceFactor"),
        expression_json=_expression_json(factor_payload),
        rationale=str(factor_payload.get("rationale") or ""),
        support_status=normalize_support_status(factor_payload.get("support_status")),
    )
    candidate.prompt_preview = build_codex_prompt(candidate)
    candidate.save(update_fields=["prompt_preview"])
    return candidate


def _expression_json(payload: dict[str, object]) -> dict[str, object]:
    expression = payload.get("expression_json")
    if isinstance(expression, dict):
        return expression
    return {"kind": "operand", "name": str(payload.get("name") or "paper_signal")}


def _fallback_factor(extraction: object) -> dict[str, object]:
    return {
        "name": "PaperEvidenceFactor",
        "expression_json": {"kind": "operand", "name": "paper_evidence_score"},
        "rationale": "Generated from extracted paper methodology for backtesting.",
        "support_status": extraction.support_status,
    }
