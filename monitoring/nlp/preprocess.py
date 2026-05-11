"""Text cleanup and tokenization for the offline NLP pipeline."""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass

WORD_PATTERN = re.compile(r"[A-Za-z][A-Za-z0-9_-]{1,}")
SENTENCE_PATTERN = re.compile(r"(?<=[.!?])\s+")


@dataclass(frozen=True, slots=True)
class TextStats:
    """Basic text size features used for cost comparisons.

    Example:
        `stats = build_text_stats("OpenAI released a report.")`
    """

    text_hash: str
    text_length: int
    token_count: int
    sentence_count: int


def normalize_text(text: str) -> str:
    """Normalize whitespace while preserving readable punctuation.

    Example:
        `normalize_text("  hello\\nworld  ")`
    """
    normalized = " ".join(text.replace("\x00", " ").split())
    if normalized:
        return normalized
    return ""


def split_sentences(text: str) -> tuple[str, ...]:
    """Split text into sentence-like chunks.

    Example:
        `split_sentences("One. Two.")`
    """
    normalized = normalize_text(text)
    parts = tuple(part.strip() for part in SENTENCE_PATTERN.split(normalized))
    return tuple(part for part in parts if part)


def tokenize_words(text: str) -> tuple[str, ...]:
    """Tokenize text into lower-case word tokens.

    Example:
        `tokenize_words("OpenAI, AI")`
    """
    tokens = WORD_PATTERN.findall(normalize_text(text))
    lowered = tuple(token.lower() for token in tokens)
    return lowered


def build_text_stats(text: str) -> TextStats:
    """Build stable text metrics for cost comparison.

    Example:
        `stats = build_text_stats("OpenAI released a report.")`
    """
    normalized = normalize_text(text)
    digest = hashlib.sha256(normalized.encode("utf-8")).hexdigest()
    return TextStats(
        text_hash=digest,
        text_length=len(normalized),
        token_count=len(tokenize_words(normalized)),
        sentence_count=len(split_sentences(normalized)),
    )
