"""Optional embeddings with simple local fallback."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass

from sourceflow.config.feature_flags import feature_flag_enabled


@dataclass(frozen=True, slots=True)
class EmbeddingResult:
    """Embedding payload and engine metadata."""

    vectors: list[list[float]]
    engine: str
    message: str


def embed_texts(texts: list[str]) -> EmbeddingResult:
    """Embed text locally, falling back to deterministic term vectors.

    Example:
        `embed_texts(["regime risk"])`
    """
    if feature_flag_enabled("RESEARCHSPACE_LOCAL_EMBEDDINGS"):
        sentence_result = _try_sentence_transformers(texts)
        if sentence_result is not None:
            return sentence_result
    vectors = [_term_frequency_vector(text) for text in texts]
    return EmbeddingResult(vectors, "simple-term-frequency", "Fallback embeddings used")


def _try_sentence_transformers(texts: list[str]) -> EmbeddingResult | None:
    try:
        from sentence_transformers import SentenceTransformer
    except ImportError:
        return None
    model = SentenceTransformer("all-MiniLM-L6-v2")
    vectors = model.encode(texts).tolist()
    return EmbeddingResult(vectors, "sentence-transformers", "Local embeddings used")


def _term_frequency_vector(text: str) -> list[float]:
    counts = Counter(_tokens(text))
    vocabulary = sorted(counts)[:128]
    return [float(counts[token]) for token in vocabulary]


def _tokens(text: str) -> list[str]:
    return [part.lower() for part in text.split() if part.strip()]
