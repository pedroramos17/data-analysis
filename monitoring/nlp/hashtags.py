"""Hashtag extraction and keyword-to-hashtag normalization."""

from __future__ import annotations

import re

HASHTAG_PATTERN = re.compile(r"#[A-Za-z0-9_]{2,}")
NON_TAG_PATTERN = re.compile(r"[^a-z0-9]+")


def extract_hashtags(text: str, keywords: tuple[str, ...] = ()) -> dict[str, object]:
    """Extract explicit tags and derive stable keyword tags.

    Example:
        `extract_hashtags("AI update #OpenAI", ("market risk",))`
    """
    explicit_tags = [tag.lower() for tag in HASHTAG_PATTERN.findall(text)]
    derived_tags = [_keyword_to_hashtag(keyword) for keyword in keywords[:8]]
    tags = tuple(dict.fromkeys(tag for tag in explicit_tags + derived_tags if tag))
    return {"backend": "keyword-normalizer", "items": list(tags), "error": ""}


def _keyword_to_hashtag(keyword: str) -> str:
    cleaned = NON_TAG_PATTERN.sub("", keyword.lower())
    if len(cleaned) < 3:
        return ""
    return f"#{cleaned[:40]}"
