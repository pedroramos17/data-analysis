"""Retraction propagation with audit rows and stale-belief recomputation.

Retracting a claim, event, or belief writes a ``RetractionLog`` audit row and
transitively marks every dependent belief stale with its own audit row. Stale
beliefs keep their last truth status until ``recompute_stale_beliefs`` (or
``recompute_belief``) re-derives it from the remaining active justifications.
"""

from __future__ import annotations

from dataclasses import dataclass

from sourceflow.tms.beliefs import recompute_belief
from sourceflow.tms.status import TmsError, TruthStatusResolution


@dataclass(frozen=True)
class RetractionResult:
    """Audit log for a retraction plus the beliefs it marked stale."""

    log: object
    stale_beliefs: list[object]


def dependent_beliefs(
    *,
    claim: object | None = None,
    event: object | None = None,
    belief: object | None = None,
) -> list[object]:
    """Return beliefs directly justified by a claim, event, or belief."""
    from sourceflow.models import Belief, Justification

    referents = {"claim": claim, "event": event, "belief": belief}
    provided = {name: record for name, record in referents.items() if record is not None}
    if len(provided) != 1:
        raise TmsError("dependent_beliefs requires exactly one of claim, event, or belief")
    name, record = next(iter(provided.items()))
    justifications = Justification.objects.filter(**{f"supporting_{name}": record})
    belief_ids = justifications.values_list("belief_id", flat=True).distinct()
    return list(Belief.objects.filter(pk__in=belief_ids))


def retract_claim(
    claim: object,
    *,
    reason: str,
    provenance: dict[str, object],
    source: object | None = None,
    document: object | None = None,
) -> RetractionResult:
    """Retract a claim, log the audit row, and mark dependent beliefs stale."""
    from sourceflow.models import Claim

    _require_inputs(reason, provenance)
    previous_status = claim.status
    claim.status = Claim.Status.RETRACTED
    claim.save(update_fields=["status", "updated_at"])
    log = _log(
        target_type="claim",
        target_id=claim.pk,
        reason=reason,
        previous_status=previous_status,
        provenance=provenance,
        source=source,
        document=document,
        affected_claim=claim,
    )
    stale = _propagate(reason=reason, provenance=provenance, claim=claim)
    return RetractionResult(log=log, stale_beliefs=stale)


def retract_event(
    event: object,
    *,
    reason: str,
    provenance: dict[str, object],
    source: object | None = None,
    document: object | None = None,
) -> RetractionResult:
    """Retract an event via its audit row and mark dependent beliefs stale.

    Events carry no status column; the ``RetractionLog`` row is the retraction
    record that ``justification_is_active`` consults.
    """
    _require_inputs(reason, provenance)
    log = _log(
        target_type="event",
        target_id=event.pk,
        reason=reason,
        previous_status="",
        provenance=provenance,
        source=source,
        document=document,
        affected_event=event,
    )
    stale = _propagate(reason=reason, provenance=provenance, event=event)
    return RetractionResult(log=log, stale_beliefs=stale)


def retract_belief(
    belief: object,
    *,
    reason: str,
    provenance: dict[str, object],
    source: object | None = None,
    document: object | None = None,
) -> RetractionResult:
    """Retract a belief, log the audit row, and mark dependent beliefs stale."""
    from sourceflow.models import Belief

    _require_inputs(reason, provenance)
    previous_status = belief.status
    belief.status = Belief.Status.RETRACTED
    belief.save(update_fields=["status", "updated_at"])
    log = _log(
        target_type="belief",
        target_id=belief.pk,
        reason=reason,
        previous_status=previous_status,
        provenance=provenance,
        source=source,
        document=document,
        affected_belief=belief,
    )
    stale = _propagate(reason=reason, provenance=provenance, belief=belief)
    return RetractionResult(log=log, stale_beliefs=stale)


def recompute_stale_beliefs() -> list[tuple[object, TruthStatusResolution]]:
    """Recompute every stale belief and reactivate it with fresh truth status."""
    from sourceflow.models import Belief

    recomputed: list[tuple[object, TruthStatusResolution]] = []
    for belief in Belief.objects.filter(status=Belief.Status.STALE):
        resolution = recompute_belief(belief)
        belief.status = Belief.Status.ACTIVE
        belief.save(update_fields=["status", "updated_at"])
        recomputed.append((belief, resolution))
    return recomputed


def _propagate(
    *,
    reason: str,
    provenance: dict[str, object],
    claim: object | None = None,
    event: object | None = None,
    belief: object | None = None,
) -> list[object]:
    from sourceflow.models import Belief

    stale: list[object] = []
    visited: set[object] = set()
    frontier = dependent_beliefs(claim=claim, event=event, belief=belief)
    while frontier:
        dependent = frontier.pop(0)
        if dependent.pk in visited:
            continue
        visited.add(dependent.pk)
        if dependent.status == Belief.Status.RETRACTED:
            continue
        previous_status = dependent.status
        dependent.status = Belief.Status.STALE
        dependent.save(update_fields=["status", "updated_at"])
        _log(
            target_type="belief",
            target_id=dependent.pk,
            reason=f"dependency retracted: {reason}",
            previous_status=previous_status,
            new_status=Belief.Status.STALE,
            provenance=provenance,
            affected_belief=dependent,
        )
        stale.append(dependent)
        frontier.extend(dependent_beliefs(belief=dependent))
    return stale


def _log(
    *,
    target_type: str,
    target_id: object,
    reason: str,
    previous_status: str,
    provenance: dict[str, object],
    new_status: str = "retracted",
    source: object | None = None,
    document: object | None = None,
    affected_claim: object | None = None,
    affected_event: object | None = None,
    affected_belief: object | None = None,
) -> object:
    from sourceflow.models import RetractionLog

    return RetractionLog.objects.create(
        target_type=target_type,
        target_id=str(target_id),
        reason=reason,
        previous_status=previous_status,
        new_status=new_status,
        source=source,
        document=document,
        affected_claim=affected_claim,
        affected_event=affected_event,
        affected_belief=affected_belief,
        provenance_json=provenance,
    )


def _require_inputs(reason: str, provenance: dict[str, object]) -> None:
    if not reason.strip():
        raise TmsError("every retraction must carry a reason")
    if not provenance:
        raise TmsError("every retraction must carry non-empty provenance")
