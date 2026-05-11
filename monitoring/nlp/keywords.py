"""Keyword extraction wrappers with YAKE and local fallback."""

from __future__ import annotations

from collections import Counter

from monitoring.nlp.preprocess import tokenize_words

STOPWORDS = {
    "about",
    "after",
    "also",
    "from",
    "into",
    "that",
    "their",
    "there",
    "this",
    "with",
}


def extract_keywords(text: str, limit: int = 12) -> dict[str, object]:
    """Extract keywords using YAKE when installed.

    Example:
        `extract_keywords("security breach report", limit=3)`
    """
    yake_result = _extract_with_yake(text, limit)
    if yake_result["items"]:
        return yake_result
    fallback_items = _frequency_keywords(text, limit)
    yake_result["items"] = fallback_items
    yake_result["backend"] = "frequency-fallback"
    return yake_result


def keyword_terms(keyword_result: object) -> tuple[str, ...]:
    """Return keyword term strings from a pipeline keyword result.

    Example:
        `keyword_terms({"items": [{"term": "security"}]})`
    """
    if not isinstance(keyword_result, dict):
        return ()
    items = keyword_result.get("items", [])
    terms = [str(item.get("term", "")) for item in items if isinstance(item, dict)]
    return tuple(term for term in terms if term)


def _extract_with_yake(text: str, limit: int) -> dict[str, object]:
    try:
        import yake
    except ImportError as error:
        return _unavailable_result("yake", error)
    extractor = yake.KeywordExtractor(lan="en", n=3, top=limit)
    items = [
        {"term": term, "score": round(float(score), 4)}
        for term, score in extractor.extract_keywords(text)
    ]
    return {"backend": "yake", "items": items, "error": ""}


def _frequency_keywords(text: str, limit: int) -> list[dict[str, object]]:
    tokens = [token for token in tokenize_words(text) if token not in STOPWORDS]
    counts = Counter(token for token in tokens if len(token) > 2)
    items = [
        {"term": term, "score": count} for term, count in counts.most_common(limit)
    ]
    return items


def _unavailable_result(backend: str, error: ImportError) -> dict[str, object]:
    return {
        "backend": f"{backend}-unavailable",
        "items": [],
        "error": f"{backend} unavailable for keyword extraction; expected installed package: {error}",
    }
