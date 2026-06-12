"""Structured claim validation."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ClaimValidationResult:
    """Validation result for a claim candidate."""

    is_valid: bool
    errors: tuple[str, ...]
    status: str


def validate_claim_candidate(candidate: object) -> ClaimValidationResult:
    """Validate minimum structured claim requirements."""
    errors: list[str] = []
    if not getattr(candidate, "subject_text", "").strip():
        errors.append("missing_subject")
    if not getattr(candidate, "predicate", "").strip():
        errors.append("missing_predicate")
    if not (
        getattr(candidate, "object_text", "").strip()
        or getattr(candidate, "object_literal", "").strip()
    ):
        errors.append("missing_object")
    if not getattr(candidate, "evidence_text", "").strip():
        errors.append("missing_evidence")
    return ClaimValidationResult(
        is_valid=not errors,
        errors=tuple(errors),
        status="active" if not errors else "incomplete",
    )
