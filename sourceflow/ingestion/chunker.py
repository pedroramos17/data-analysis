"""Canonical document chunking helpers."""

from __future__ import annotations

from dataclasses import dataclass

from sourceflow.ingestion.dedup import content_hash


@dataclass(frozen=True)
class ChunkSpec:
    """A chunk of document text with parent-text offsets."""

    chunk_index: int
    text: str
    char_start: int
    char_end: int
    token_count: int
    content_hash: str


def chunk_text(text: str, *, max_chars: int = 2_000, overlap: int = 200) -> list[ChunkSpec]:
    """Split text into offset-preserving chunks.

    Chunks prefer whitespace boundaries and keep bounded overlap for later
    retrieval. Offsets always refer to the original input text.
    """
    if max_chars <= 0:
        raise ValueError("max_chars must be positive")
    if overlap < 0:
        raise ValueError("overlap must be non-negative")
    if overlap >= max_chars:
        raise ValueError("overlap must be smaller than max_chars")

    if not text:
        return []
    chunks: list[ChunkSpec] = []
    start = 0
    while start < len(text):
        end = _chunk_end(text, start, max_chars)
        chunk = text[start:end].strip()
        if chunk:
            leading = len(text[start:end]) - len(text[start:end].lstrip())
            trailing = len(text[start:end].rstrip())
            actual_start = start + leading
            actual_end = start + trailing
            chunks.append(
                ChunkSpec(
                    chunk_index=len(chunks),
                    text=chunk,
                    char_start=actual_start,
                    char_end=actual_end,
                    token_count=len(chunk.split()),
                    content_hash=content_hash(chunk),
                )
            )
        if end >= len(text):
            break
        start = max(end - overlap, start + 1)
    return chunks


def chunk_containing_span(
    chunks: list[ChunkSpec],
    char_start: int,
    char_end: int,
) -> ChunkSpec | None:
    """Return the first chunk containing a character span."""
    for chunk in chunks:
        if chunk.char_start <= char_start and char_end <= chunk.char_end:
            return chunk
    for chunk in chunks:
        if chunk.char_start <= char_start < chunk.char_end:
            return chunk
    return None


def _chunk_end(text: str, start: int, max_chars: int) -> int:
    hard_end = min(start + max_chars, len(text))
    if hard_end >= len(text):
        return len(text)
    boundary = text.rfind(" ", start + max_chars // 2, hard_end)
    if boundary <= start:
        boundary = text.rfind("\n", start + max_chars // 2, hard_end)
    if boundary <= start:
        return hard_end
    return boundary
