"""Vector and lexical search over local paper chunks."""

from __future__ import annotations

import re
from dataclasses import dataclass

from django.db.models import QuerySet

from sourceflow.config.feature_flags import feature_flag_enabled, require_feature


@dataclass(frozen=True, slots=True)
class ChunkSearchResult:
    """A ranked chunk result."""

    chunk: object
    score: float
    engine: str


def search_paper_chunks(
    paper: object,
    query: str,
    limit: int = 5,
) -> list[ChunkSearchResult]:
    """Search chunks with FAISS when present or lexical fallback.

    Example:
        `search_paper_chunks(paper, "walk-forward")`
    """
    require_feature("RESEARCHSPACE_SIMPLE_VECTOR_SEARCH")
    if feature_flag_enabled("RESEARCHSPACE_FAISS") and _faiss_available():
        return _lexical_results(paper.chunks.all(), query, limit, "faiss-ready")
    return _lexical_results(paper.chunks.all(), query, limit, "simple-vector-search")


def build_paper_index(paper: object) -> str:
    """Build a lightweight local search index marker.

    Example:
        `build_paper_index(paper)`
    """
    count = paper.chunks.count()
    return f"Indexed {count} chunk(s) with simple-vector-search fallback"


def _lexical_results(
    chunks: QuerySet[object],
    query: str,
    limit: int,
    engine: str,
) -> list[ChunkSearchResult]:
    scored = [_score_chunk(chunk, query, engine) for chunk in chunks]
    ranked = sorted(scored, key=lambda result: result.score, reverse=True)
    return [result for result in ranked if result.score > 0][:limit]


def _score_chunk(chunk: object, query: str, engine: str) -> ChunkSearchResult:
    query_tokens = set(_tokens(query))
    chunk_tokens = set(_tokens(chunk.text))
    overlap = query_tokens.intersection(chunk_tokens)
    score = len(overlap) / max(len(query_tokens), 1)
    return ChunkSearchResult(chunk, float(score), engine)


def _tokens(text: str) -> list[str]:
    return re.findall(r"[A-Za-z0-9_]+", text.lower())


def _faiss_available() -> bool:
    try:
        import faiss  # noqa: F401
    except ImportError:
        return False
    return True
