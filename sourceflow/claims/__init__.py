"""Agentic claim extraction and comparison boundary."""

from sourceflow.claims.comparison import (
    SourceClaimComparison,
    SourceClaimSummary,
    compare_event_cluster_claims,
)
from sourceflow.claims.extractor import (
    ClaimCandidate,
    ClaimExtractor,
    HeuristicClaimExtractor,
    PersistedClaimResult,
    extract_and_persist_document_claims,
    extract_claims,
    persist_claim_candidates,
)
from sourceflow.claims.normalizer import (
    infer_modality,
    infer_polarity,
    infer_tense,
    normalize_object_literal,
    normalize_predicate,
)
from sourceflow.claims.validators import ClaimValidationResult, validate_claim_candidate

__all__ = [
    "ClaimCandidate",
    "ClaimExtractor",
    "ClaimValidationResult",
    "HeuristicClaimExtractor",
    "PersistedClaimResult",
    "SourceClaimComparison",
    "SourceClaimSummary",
    "compare_event_cluster_claims",
    "extract_and_persist_document_claims",
    "extract_claims",
    "infer_modality",
    "infer_polarity",
    "infer_tense",
    "normalize_object_literal",
    "normalize_predicate",
    "persist_claim_candidates",
    "validate_claim_candidate",
]
