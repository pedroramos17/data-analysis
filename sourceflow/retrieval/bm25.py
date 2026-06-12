"""Dependency-light BM25 retrieval for document chunks."""

from __future__ import annotations

import math
import re
from collections import Counter
from dataclasses import dataclass, field
from typing import Iterable, Mapping

TOKEN_PATTERN = re.compile(r"[a-z0-9]+")


@dataclass(frozen=True)
class TextDocument:
    """Small text document wrapper used by dependency-light indexes."""

    identifier: str
    text: str
    payload: object | None = None
    provenance: Mapping[str, object] = field(default_factory=dict)


@dataclass(frozen=True)
class RetrievalHit:
    """One scored retrieval hit."""

    identifier: str
    score: float
    text: str
    payload: object | None = None
    provenance: Mapping[str, object] = field(default_factory=dict)
    retriever: str = "bm25"


class BM25Index:
    """Small in-memory BM25 index for local-first retrieval."""

    def __init__(self, documents: Iterable[TextDocument], *, k1: float = 1.5, b: float = 0.75) -> None:
        self.documents = tuple(documents)
        self.k1 = k1
        self.b = b
        self.doc_tokens = tuple(tokenize(document.text) for document in self.documents)
        self.term_counts = tuple(Counter(tokens) for tokens in self.doc_tokens)
        self.doc_lengths = tuple(len(tokens) for tokens in self.doc_tokens)
        self.avg_doc_length = sum(self.doc_lengths) / len(self.doc_lengths) if self.doc_lengths else 0.0
        self.doc_frequency = Counter()
        for counts in self.term_counts:
            self.doc_frequency.update(counts.keys())

    def search(self, query: str, *, limit: int = 10) -> list[RetrievalHit]:
        """Return BM25-ranked hits for query."""
        query_terms = tokenize(query)
        hits: list[RetrievalHit] = []
        for index, document in enumerate(self.documents):
            score = self._score(query_terms, index)
            if score <= 0:
                continue
            hits.append(
                RetrievalHit(
                    identifier=document.identifier,
                    score=score,
                    text=document.text,
                    payload=document.payload,
                    provenance=document.provenance,
                    retriever="bm25",
                )
            )
        return sorted(hits, key=lambda hit: hit.score, reverse=True)[:limit]

    def _score(self, query_terms: list[str], index: int) -> float:
        if not query_terms or not self.documents:
            return 0.0
        score = 0.0
        counts = self.term_counts[index]
        doc_length = self.doc_lengths[index]
        for term in query_terms:
            frequency = counts.get(term, 0)
            if frequency == 0:
                continue
            idf = math.log(1 + (len(self.documents) - self.doc_frequency[term] + 0.5) / (self.doc_frequency[term] + 0.5))
            denominator = frequency + self.k1 * (1 - self.b + self.b * doc_length / (self.avg_doc_length or 1))
            score += idf * (frequency * (self.k1 + 1)) / denominator
        return score


def tokenize(text: str) -> list[str]:
    """Tokenize text for local lexical retrieval."""
    return TOKEN_PATTERN.findall(text.lower())


def documents_from_chunks(chunks: Iterable[object]) -> list[TextDocument]:
    """Convert Django DocumentChunk-like records into text documents."""
    documents: list[TextDocument] = []
    for chunk in chunks:
        document = _value(chunk, "document") or {}
        source = _value(document, "source") or {}
        documents.append(
            TextDocument(
                identifier=str(_value(chunk, "pk") or _value(chunk, "id")),
                text=str(_value(chunk, "text") or ""),
                payload=chunk,
                provenance={
                    "chunk_id": _value(chunk, "pk") or _value(chunk, "id"),
                    "document_id": _value(chunk, "document_id") or _value(document, "pk") or _value(document, "id"),
                    "source_id": _value(document, "source_id") or _value(source, "pk") or _value(source, "id"),
                    "char_start": _value(chunk, "char_start"),
                    "char_end": _value(chunk, "char_end"),
                },
            )
        )
    return documents


def search_chunks_bm25(query: str, chunks: Iterable[object], *, limit: int = 10) -> list[RetrievalHit]:
    """Search chunk-like records with BM25."""
    return BM25Index(documents_from_chunks(chunks)).search(query, limit=limit)


def _value(record: object, key: str) -> object:
    return record.get(key, "") if isinstance(record, dict) else getattr(record, key, "")
