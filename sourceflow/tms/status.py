"""Truth status resolution for the truth maintenance system.

The resolver is intentionally dependency-light so belief recomputation policy
can be unit tested and shared without importing Django models. Contradictory
evidence marks a dispute state; it is never collapsed into one truth value and
never raises during inference.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Iterable

from sourceflow.reasoning.assumptions import AssumptionPolicyCode, evaluate_missing_fact

SUPPORTING_TYPES = frozenset({"supports", "derived_by_rule", "assumption"})
CONTRADICTING_TYPES = frozenset({"contradicts"})
JUSTIFICATION_TYPES = SUPPORTING_TYPES | CONTRADICTING_TYPES
DEFAULT_FULL_SUPPORT_WEIGHT = Decimal("1")
_CONFIDENCE_QUANTUM = Decimal("0.01")


class TmsError(ValueError):
    """Raised for invalid truth maintenance inputs."""


@dataclass(frozen=True)
class JustificationInput:
    """Dependency-light view of one justification edge."""

    support_type: str
    weight: Decimal = Decimal("1")
    is_active: bool = True


@dataclass(frozen=True)
class TruthStatusResolution:
    """Computed truth status with evidence weights and explanation."""

    truth_status: str
    confidence: Decimal
    supporting_weight: Decimal
    contradicting_weight: Decimal
    is_disputed: bool
    explanation: str


def resolve_truth_status(
    justifications: Iterable[JustificationInput],
    *,
    policy: str | AssumptionPolicyCode = AssumptionPolicyCode.OWA,
    full_support_weight: Decimal = DEFAULT_FULL_SUPPORT_WEIGHT,
) -> TruthStatusResolution:
    """Resolve a belief's truth status from its active justifications.

    With no active justifications the assumption policy decides: OWA keeps the
    belief unknown while CWA may infer supported absence. Mixed supporting and
    contradicting evidence yields a contradicted, disputed status.
    """
    if full_support_weight <= 0:
        raise TmsError("full_support_weight must be positive")
    supporting = Decimal("0")
    contradicting = Decimal("0")
    for justification in justifications:
        if justification.support_type not in JUSTIFICATION_TYPES:
            raise TmsError(f"unknown support type: {justification.support_type!r}")
        if justification.weight < 0:
            raise TmsError("justification weight must be non-negative")
        if not justification.is_active:
            continue
        if justification.support_type in CONTRADICTING_TYPES:
            contradicting += justification.weight
        else:
            supporting += justification.weight

    if supporting == 0 and contradicting == 0:
        missing = evaluate_missing_fact(policy)
        return TruthStatusResolution(
            truth_status=missing.truth_status,
            confidence=Decimal("0"),
            supporting_weight=supporting,
            contradicting_weight=contradicting,
            is_disputed=False,
            explanation=missing.explanation,
        )
    if supporting > 0 and contradicting > 0:
        return TruthStatusResolution(
            truth_status="contradicted",
            confidence=_ratio(supporting, supporting + contradicting),
            supporting_weight=supporting,
            contradicting_weight=contradicting,
            is_disputed=True,
            explanation="Supporting and contradicting evidence coexist; dispute is preserved.",
        )
    if contradicting > 0:
        return TruthStatusResolution(
            truth_status="false_supported",
            confidence=_strength(contradicting, full_support_weight),
            supporting_weight=supporting,
            contradicting_weight=contradicting,
            is_disputed=False,
            explanation="Only contradicting evidence is active.",
        )
    if supporting < full_support_weight:
        return TruthStatusResolution(
            truth_status="partially_supported",
            confidence=_strength(supporting, full_support_weight),
            supporting_weight=supporting,
            contradicting_weight=contradicting,
            is_disputed=False,
            explanation="Supporting evidence is below the full-support weight.",
        )
    return TruthStatusResolution(
        truth_status="true_supported",
        confidence=_strength(supporting, full_support_weight),
        supporting_weight=supporting,
        contradicting_weight=contradicting,
        is_disputed=False,
        explanation="Supporting evidence meets the full-support weight.",
    )


def _ratio(part: Decimal, whole: Decimal) -> Decimal:
    return (part / whole).quantize(_CONFIDENCE_QUANTUM)


def _strength(weight: Decimal, full_support_weight: Decimal) -> Decimal:
    return min(Decimal("1"), (weight / full_support_weight).quantize(_CONFIDENCE_QUANTUM))
