"""Pluggable article embedding helpers with a local deterministic backend."""

import hashlib
import math
import re
from dataclasses import dataclass
from typing import Protocol

from monitoring.models import ArticleEmbedding, NormalizedDocument
from monitoring.services.deduplication import content_hash

TOKEN_PATTERN = re.compile(r"[a-z0-9][a-z0-9_.-]{1,}")
DEFAULT_DIMENSIONS = 128


@dataclass(frozen=True, slots=True)
class EmbeddingResult:
    """One embedding vector returned by a backend."""

    backend: str
    model_name: str
    vector: tuple[float, ...]
    metadata: dict[str, object]


class EmbeddingBackend(Protocol):
    """Backend interface for article embeddings."""

    backend_name: str
    model_name: str

    def embed(self, text: str) -> EmbeddingResult:
        """Embed article text.

        Example:
            `backend.embed("article text")`
        """


class LocalHashEmbeddingBackend:
    """Token-hash embedding that runs offline."""

    backend_name = "local_hash"
    model_name = "token-hash-v1"

    def embed(self, text: str) -> EmbeddingResult:
        """Embed text into a sparse normalized hash vector.

        Example:
            `LocalHashEmbeddingBackend().embed("OpenAI Paris")`
        """
        vector = _normalized_hash_vector(text, DEFAULT_DIMENSIONS)
        return EmbeddingResult(self.backend_name, self.model_name, vector, {})


def embed_article(
    article: NormalizedDocument,
    backend: EmbeddingBackend | None = None,
) -> ArticleEmbedding:
    """Create or update one article embedding.

    Example:
        `embedding = embed_article(article)`
    """
    embedder = backend or LocalHashEmbeddingBackend()
    text = _article_embedding_text(article)
    result = embedder.embed(text)
    embedding, _created = ArticleEmbedding.objects.update_or_create(
        article=article,
        backend=result.backend,
        defaults=_embedding_defaults(result, text),
    )
    return embedding


def article_vector(article: NormalizedDocument) -> list[float]:
    """Return the default article vector or an empty list.

    Example:
        `article_vector(article)`
    """
    embedding = ArticleEmbedding.objects.filter(article=article).first()
    return [float(value) for value in embedding.vector] if embedding else []


def cosine_similarity(first: list[float], second: list[float]) -> float:
    """Compute cosine similarity for equal-length vectors.

    Example:
        `cosine_similarity([1.0], [1.0])`
    """
    if not first or not second or len(first) != len(second):
        return 0.0
    return round(sum(a * b for a, b in zip(first, second, strict=True)), 4)


def _article_embedding_text(article: NormalizedDocument) -> str:
    text = article.extracted_text or article.text or article.content
    return " ".join([article.title, text])


def _embedding_defaults(result: EmbeddingResult, text: str) -> dict[str, object]:
    return {
        "model_name": result.model_name,
        "vector": list(result.vector),
        "dimensions": len(result.vector),
        "text_hash": content_hash(text),
        "metadata": result.metadata,
    }


def _normalized_hash_vector(text: str, dimensions: int) -> tuple[float, ...]:
    values = [0.0] * dimensions
    for token in TOKEN_PATTERN.findall(text.lower()):
        values[_token_bucket(token, dimensions)] += 1.0
    return _normalize(values)


def _token_bucket(token: str, dimensions: int) -> int:
    digest = hashlib.sha256(token.encode("utf-8")).hexdigest()
    return int(digest[:8], 16) % dimensions


def _normalize(values: list[float]) -> tuple[float, ...]:
    magnitude = math.sqrt(sum(value * value for value in values))
    if magnitude == 0:
        return tuple(values)
    return tuple(round(value / magnitude, 6) for value in values)
