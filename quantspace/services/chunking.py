"""Page-aware chunking for local research papers."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ChunkDraft:
    """Text prepared for a PaperChunk row."""

    chunk_index: int
    page_start: int
    page_end: int
    text: str
    token_count: int


def chunk_page_texts(
    page_texts: list[tuple[int, str]],
    max_chars: int = 1800,
) -> list[ChunkDraft]:
    """Merge page text into chunks while preserving page ranges.

    Example:
        `chunk_page_texts([(1, "alpha"), (2, "beta")])`
    """
    drafts: list[ChunkDraft] = []
    current_text = ""
    current_start = 0
    current_end = 0
    for page_number, page_text in page_texts:
        next_text = _joined_text(current_text, page_text)
        if current_text and len(next_text) > max_chars:
            drafts.append(_draft(len(drafts), current_start, current_end, current_text))
            current_text, current_start = page_text.strip(), page_number
        else:
            current_text = next_text
            current_start = current_start or page_number
        current_end = page_number
    if current_text:
        drafts.append(_draft(len(drafts), current_start, current_end, current_text))
    return drafts


def _joined_text(left: str, right: str) -> str:
    stripped = right.strip()
    if not left:
        return stripped
    return f"{left}\n{stripped}"


def _draft(index: int, page_start: int, page_end: int, text: str) -> ChunkDraft:
    return ChunkDraft(index, page_start, page_end, text, len(text.split()))
