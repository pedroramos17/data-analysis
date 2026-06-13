"""Belief creation and recomputation with mandatory justifications.

Every belief carries a resolved assumption policy and at least one
justification row linking it to supporting or contradicting claims, events,
beliefs, or rules. Truth status is always recomputed from the active
justifications, so retractions can be propagated without rewriting history.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

from sourceflow.reasoning.assumptions import AssumptionPolicyCode, resolve_assumption_policy
from sourceflow.tms.status import (
    JustificationInput,
    TmsError,
    TruthStatusResolution,
    resolve_truth_status,
)


@dataclass(frozen=True)
class JustificationSpec:
    """One justification edge to attach to a belief."""

    support_type: str
    claim: object | None = None
    event: object | None = None
    belief: object | None = None
    rule: object | None = None
    weight: Decimal = Decimal("1")


def ensure_assumption_policy(code: str | AssumptionPolicyCode) -> object:
    """Return the persisted assumption policy row for a policy code."""
    from sourceflow.models import AssumptionPolicy

    normalized = AssumptionPolicyCode(str(code))
    policy, _created = AssumptionPolicy.objects.get_or_create(
        code=normalized.value,
        defaults={
            "name": AssumptionPolicy.PolicyCode(normalized.value).label,
            "provenance_json": {"created_by": "sourceflow.tms.beliefs"},
        },
    )
    return policy


def create_belief(
    *,
    belief_type: str,
    predicate: str,
    justifications: list[JustificationSpec],
    provenance: dict[str, object],
    subject_entity: object | None = None,
    object_entity: object | None = None,
    object_literal: str = "",
    context: str = "news",
    policy_code: str | AssumptionPolicyCode | None = None,
    created_by_rule: object | None = None,
    valid_from: datetime | None = None,
    valid_until: datetime | None = None,
) -> object:
    """Create a belief with justification rows and a computed truth status."""
    from sourceflow.models import Belief, Justification

    if not provenance:
        raise TmsError("every belief must carry non-empty provenance")
    if not justifications:
        raise TmsError("every belief must carry at least one justification")
    for spec in justifications:
        _validate_spec(spec)

    policy = ensure_assumption_policy(policy_code or resolve_assumption_policy(context))
    belief = Belief.objects.create(
        belief_type=belief_type,
        subject_entity=subject_entity,
        predicate=predicate,
        object_entity=object_entity,
        object_literal=object_literal,
        assumption_policy=policy,
        created_by_rule=created_by_rule,
        valid_from=valid_from,
        valid_until=valid_until,
        provenance_json=provenance,
    )
    for spec in justifications:
        Justification.objects.create(
            belief=belief,
            support_type=spec.support_type,
            supporting_claim=spec.claim,
            supporting_event=spec.event,
            supporting_belief=spec.belief,
            rule=spec.rule,
            weight=spec.weight,
            provenance_json=provenance,
        )
    recompute_belief(belief)
    return belief


def recompute_belief(belief: object) -> TruthStatusResolution:
    """Recompute and persist a belief's truth status from active justifications."""
    inputs = [
        JustificationInput(
            support_type=justification.support_type,
            weight=Decimal(justification.weight),
            is_active=justification_is_active(justification),
        )
        for justification in belief.justifications.all()
    ]
    resolution = resolve_truth_status(inputs, policy=belief.assumption_policy.code)
    belief.truth_status = resolution.truth_status
    belief.confidence = resolution.confidence
    belief.save(update_fields=["truth_status", "confidence", "updated_at"])
    return resolution


def justification_is_active(justification: object) -> bool:
    """Return whether a justification still counts toward truth status.

    A justification goes inactive when its supporting claim or belief is
    retracted, its supporting event has a retraction audit row, its rule is
    disabled, or every referenced record was severed. Assumptions stay active
    without a referent.
    """
    from sourceflow.models import Belief, Claim, Justification, RetractionLog

    if justification.rule is not None and not justification.rule.is_active:
        return False
    if justification.supporting_claim is not None:
        return justification.supporting_claim.status != Claim.Status.RETRACTED
    if justification.supporting_belief is not None:
        return justification.supporting_belief.status != Belief.Status.RETRACTED
    if justification.supporting_event is not None:
        return not RetractionLog.objects.filter(
            affected_event=justification.supporting_event,
            new_status="retracted",
        ).exists()
    if justification.rule is not None:
        return True
    return justification.support_type == Justification.SupportType.ASSUMPTION


def _validate_spec(spec: JustificationSpec) -> None:
    from sourceflow.models import Justification

    if spec.support_type not in Justification.SupportType.values:
        raise TmsError(f"unknown support type: {spec.support_type!r}")
    if spec.weight < 0:
        raise TmsError("justification weight must be non-negative")
    has_referent = any(value is not None for value in (spec.claim, spec.event, spec.belief, spec.rule))
    if not has_referent and spec.support_type != Justification.SupportType.ASSUMPTION:
        raise TmsError("non-assumption justifications must reference a claim, event, belief, or rule")
