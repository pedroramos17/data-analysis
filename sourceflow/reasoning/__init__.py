"""Agentic reasoning and assumption policy boundary."""

from sourceflow.reasoning.engine import (
    InferenceEngine,
    InferenceEngineError,
    InferenceResult,
    upsert_inference_rule,
)
from sourceflow.reasoning.contradictions import (
    DISPUTE_STATUS,
    ClaimKey,
    ContradictionResult,
    claim_key,
    claims_contradict,
    detect_claim_contradictions,
    explain_contradiction,
    find_contradictory_claim_pairs,
    support_is_disputed,
)
from sourceflow.reasoning.diagnosis import (
    AnomalyInput,
    DiagnosisHypothesis,
    EvidenceReference,
    diagnose_anomaly,
    diagnose_stock_move,
)
from sourceflow.reasoning.rules import (
    RULE_TYPES,
    RuleAction,
    RuleCondition,
    RuleDefinition,
    RuleDefinitionError,
    field_value,
    load_rule_definitions,
    value_matches,
)

__all__ = [
    "RULE_TYPES",
    "DISPUTE_STATUS",
    "AnomalyInput",
    "ClaimKey",
    "ContradictionResult",
    "DiagnosisHypothesis",
    "EvidenceReference",
    "InferenceEngine",
    "InferenceEngineError",
    "InferenceResult",
    "RuleAction",
    "RuleCondition",
    "RuleDefinition",
    "RuleDefinitionError",
    "claim_key",
    "claims_contradict",
    "detect_claim_contradictions",
    "diagnose_anomaly",
    "diagnose_stock_move",
    "explain_contradiction",
    "field_value",
    "find_contradictory_claim_pairs",
    "load_rule_definitions",
    "support_is_disputed",
    "upsert_inference_rule",
    "value_matches",
]
