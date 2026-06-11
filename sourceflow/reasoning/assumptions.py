"""Assumption policy resolution for canonical reasoning.

The resolver is intentionally dependency-light so ingestion, extraction, CLI,
background jobs, and API handlers can share the same policy decisions without
importing Django models.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class AssumptionPolicyCode(StrEnum):
    """Supported assumption policy identifiers."""

    OWA = "OWA"
    CWA = "CWA"
    PARTIAL_CWA = "PartialCWA"
    CAREFUL_CWA = "CarefulCWA"
    GCWA = "GCWA"
    EGCWA = "EGCWA"
    EXTENDED_CWA = "ExtendedCWA"
    UNIQUE_NAME = "UniqueNameAssumption"
    NO_UNIQUE_NAME = "NoUniqueNameAssumption"


@dataclass(frozen=True)
class MissingFactEvaluation:
    """Result of evaluating a missing fact under an assumption policy."""

    policy: AssumptionPolicyCode
    truth_status: str
    can_infer_absence: bool
    explanation: str


NEWS_CONTEXTS = frozenset(
    {
        "article",
        "document",
        "news",
        "news_article",
        "public_source",
        "source_claim",
    }
)
CONTROLLED_INTERNAL_CONTEXTS = frozenset(
    {
        "backtest_run",
        "internal_table",
        "job",
        "jobs",
        "pipeline_task",
        "portfolio_position",
        "portfolio_positions",
        "trade",
        "trades",
    }
)
SOURCE_COVERAGE_CONTEXTS = frozenset(
    {
        "coverage",
        "event_coverage",
        "omission",
        "source_comparison",
        "source_coverage",
    }
)
UNIQUE_NAME_IDENTIFIERS = frozenset({"ticker", "isin", "lei", "cnpj"})


def resolve_assumption_policy(
    context: str,
    *,
    identifier_type: str = "",
    ambiguous_name: bool = False,
) -> AssumptionPolicyCode:
    """Return the default policy for a reasoning context.

    Example:
        `resolve_assumption_policy("news") == AssumptionPolicyCode.OWA`
    """
    normalized_identifier = _normalize(identifier_type)
    if normalized_identifier in UNIQUE_NAME_IDENTIFIERS:
        return AssumptionPolicyCode.UNIQUE_NAME
    if ambiguous_name:
        return AssumptionPolicyCode.NO_UNIQUE_NAME

    normalized_context = _normalize(context)
    if normalized_context in SOURCE_COVERAGE_CONTEXTS:
        return AssumptionPolicyCode.PARTIAL_CWA
    if normalized_context in CONTROLLED_INTERNAL_CONTEXTS:
        return AssumptionPolicyCode.CWA
    if normalized_context in NEWS_CONTEXTS:
        return AssumptionPolicyCode.OWA
    return AssumptionPolicyCode.OWA


def evaluate_missing_fact(policy: str | AssumptionPolicyCode) -> MissingFactEvaluation:
    """Evaluate whether a missing fact implies absence under a policy.

    OWA keeps missing facts unknown. CWA can infer supported absence for controlled
    internal tables. PartialCWA can report scoped omission without making the
    omitted fact globally false.
    """
    code = AssumptionPolicyCode(str(policy))
    if code == AssumptionPolicyCode.CWA:
        return MissingFactEvaluation(
            policy=code,
            truth_status="false_supported",
            can_infer_absence=True,
            explanation="Controlled closed-world context supports absence inference.",
        )
    if code == AssumptionPolicyCode.PARTIAL_CWA:
        return MissingFactEvaluation(
            policy=code,
            truth_status="unknown",
            can_infer_absence=False,
            explanation="Scoped source coverage can indicate omission, not global falsity.",
        )
    return MissingFactEvaluation(
        policy=code,
        truth_status="unknown",
        can_infer_absence=False,
        explanation="Open-world context keeps omitted facts unknown.",
    )


def _normalize(value: str) -> str:
    return value.strip().lower().replace("-", "_").replace(" ", "_")
