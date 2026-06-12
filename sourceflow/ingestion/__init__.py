"""Agentic ingestion boundary for source adapters."""

from sourceflow.ingestion.chunker import ChunkSpec, chunk_containing_span, chunk_text
from sourceflow.ingestion.dedup import (
    DuplicateCheck,
    canonicalize_url,
    content_hash,
    detect_duplicate_hash,
    document_content_hash,
    document_dedupe_key,
    normalize_text,
)
from sourceflow.ingestion.evidence import (
    EvidenceSpanSpec,
    create_evidence_span_for_document,
    evidence_for_belief,
    evidence_for_claim,
    extract_evidence_span,
)
from sourceflow.ingestion.normalizer import (
    DEFAULT_INGESTION_VERSION,
    DocumentInput,
    NormalizedDocument,
    PersistedDocumentResult,
    normalize_document_input,
    persist_normalized_document,
)

__all__ = [
    "ChunkSpec",
    "DEFAULT_INGESTION_VERSION",
    "DocumentInput",
    "DuplicateCheck",
    "EvidenceSpanSpec",
    "NormalizedDocument",
    "PersistedDocumentResult",
    "canonicalize_url",
    "chunk_containing_span",
    "chunk_text",
    "content_hash",
    "create_evidence_span_for_document",
    "detect_duplicate_hash",
    "document_content_hash",
    "document_dedupe_key",
    "evidence_for_belief",
    "evidence_for_claim",
    "extract_evidence_span",
    "normalize_document_input",
    "normalize_text",
    "persist_normalized_document",
]
