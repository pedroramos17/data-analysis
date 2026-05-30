"""Codex prompt export for QuantSpace factor candidates."""

from __future__ import annotations

from sourceflow.config.feature_flags import require_feature

FORBIDDEN_CLAIMS = ("profit", "profitable", "guarantee", "alpha claim")


def build_codex_prompt(candidate: object) -> str:
    """Build a research-only implementation prompt for one candidate.

    Example:
        `build_codex_prompt(candidate)`
    """
    require_feature("QUANTSPACE_CODEX_PROMPT_EXPORT")
    prompt = (
        "Implement this Sourceflow symbolic factor candidate as research code.\n"
        f"Name: {candidate.name}\n"
        f"Status: {candidate.status}\n"
        f"Support status: {candidate.support_status}\n"
        f"Expression JSON: {candidate.expression_json}\n"
        "Rules: no paid API dependency, no live trading, no causal claims, "
        "benchmark against simple baselines, preserve NEEDS_BACKTEST framing."
    )
    return _remove_forbidden_claims(prompt)


def export_candidate_prompt(candidate: object) -> object:
    """Persist a prompt export artifact for one factor candidate.

    Example:
        `export_candidate_prompt(candidate)`
    """
    from quantspace.models import PaperArtifact

    content = build_codex_prompt(candidate)
    return PaperArtifact.objects.create(
        paper=candidate.paper,
        artifact_type="codex_prompt",
        content=content,
        support_status=candidate.support_status,
    )


def _remove_forbidden_claims(prompt: str) -> str:
    cleaned = prompt
    for claim in FORBIDDEN_CLAIMS:
        cleaned = cleaned.replace(claim, "research signal")
        cleaned = cleaned.replace(claim.title(), "Research signal")
    return cleaned
