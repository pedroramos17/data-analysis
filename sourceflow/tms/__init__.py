"""Agentic truth-maintenance boundary."""

from sourceflow.tms.beliefs import (
    JustificationSpec,
    create_belief,
    ensure_assumption_policy,
    justification_is_active,
    recompute_belief,
)
from sourceflow.tms.retraction import (
    RetractionResult,
    dependent_beliefs,
    recompute_stale_beliefs,
    retract_belief,
    retract_claim,
    retract_event,
)
from sourceflow.tms.status import (
    CONTRADICTING_TYPES,
    DEFAULT_FULL_SUPPORT_WEIGHT,
    JUSTIFICATION_TYPES,
    SUPPORTING_TYPES,
    JustificationInput,
    TmsError,
    TruthStatusResolution,
    resolve_truth_status,
)

__all__ = [
    "CONTRADICTING_TYPES",
    "DEFAULT_FULL_SUPPORT_WEIGHT",
    "JUSTIFICATION_TYPES",
    "SUPPORTING_TYPES",
    "JustificationInput",
    "JustificationSpec",
    "RetractionResult",
    "TmsError",
    "TruthStatusResolution",
    "create_belief",
    "dependent_beliefs",
    "ensure_assumption_policy",
    "justification_is_active",
    "recompute_belief",
    "recompute_stale_beliefs",
    "resolve_truth_status",
    "retract_belief",
    "retract_claim",
    "retract_event",
]
