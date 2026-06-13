"""Deterministic local vector retrieval for document chunks."""

from __future__ import annotations

import math
from collections import Counter
from typing import Iterable

from sourceflow.retrieval.bm25 import RetrievalHit, TextDocument, documents_from_chunks, tokenize


def vectorize_text(text: str) -> dict[str, float]:
    """Return a normalized sparse token vector."""
    counts = Counter(tokenize(text))
    norm = math.sqrt(sum(value * value for value in counts.values()))
    if norm == 0:
        return {}
    return {token: value / norm for token, value in counts.items()}


def cosine_similarity(left: dict[str, float], right: dict[str, float]) -> float:
    """Return cosine similarity for sparse vectors."""
    if not left or not right:
        return 0.0
    if len(left) > len(right):
        left, right = right, left
    return sum(value * right.get(token, 0.0) for token, value in left.items())


class VectorIndex:
    """In-memory deterministic sparse-vector index."""

    def __init__(self, documents: Iterable[TextDocument]) -> None:
        self.documents = tuple(documents)
        self.vectors = tuple(vectorize_text(document.text) for document in self.documents)

    def search(self, query: str, *, limit: int = 10) -> list[RetrievalHit]:
        """Return vector-similarity ranked hits for query."""
        query_vector = vectorize_text(query)
        hits: list[RetrievalHit] = []
        for document, vector in zip(self.documents, self.vectors, strict=True):
            score = cosine_similarity(query_vector, vector)
            if score <= 0:
                continue
            hits.append(
                RetrievalHit(
                    identifier=document.identifier,
                    score=score,
                    text=document.text,
                    payload=document.payload,
                    provenance=document.provenance,
                    retriever="vector",
                )
            )
        return sorted(hits, key=lambda hit: hit.score, reverse=True)[:limit]


def search_chunks_vector(query: str, chunks: Iterable[object], *, limit: int = 10) -> list[RetrievalHit]:
    """Search chunk-like records with deterministic vector similarity."""
    return VectorIndex(documents_from_chunks(chunks)).search(query, limit=limit)
