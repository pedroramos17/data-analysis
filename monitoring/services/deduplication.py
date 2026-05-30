"""Deterministic URL, content, and near-duplicate helpers."""

import hashlib
import re
from collections import Counter

from monitoring.normalizers import canonicalize_url

TOKEN_PATTERN = re.compile(r"[a-z0-9][a-z0-9_.-]{1,}")
SIMHASH_BITS = 64


def canonicalize_article_url(raw_url: str) -> str:
    """Return the article canonical URL used by comparison features.

    Example:
        `canonicalize_article_url("https://example.org/a/?utm_source=x")`
    """
    canonical_url = canonicalize_url(raw_url)
    return _strip_trailing_path_slash(canonical_url)


def url_hash(raw_url: str) -> str:
    """Hash a canonical article URL.

    Example:
        `url_hash("https://example.org/a")`
    """
    return _sha256(canonicalize_article_url(raw_url))


def content_hash(text: str) -> str:
    """Hash normalized article content.

    Example:
        `content_hash("A  claim")`
    """
    return _sha256(normalize_dedupe_text(text))


def simhash_text(text: str) -> str:
    """Compute a 64-bit token simhash as lowercase hex.

    Example:
        `simhash_text("OpenAI launched a model")`
    """
    tokens = _dedupe_tokens(text)
    if not tokens:
        return content_hash(text)[:16]
    value = _weighted_simhash_value(Counter(tokens))
    return f"{value:016x}"


def hamming_distance(first_hash: str, second_hash: str) -> int:
    """Count differing bits between two hex simhash strings.

    Example:
        `hamming_distance("0f", "00")`
    """
    first_value = int(first_hash or "0", 16)
    second_value = int(second_hash or "0", 16)
    return (first_value ^ second_value).bit_count()


def normalize_dedupe_text(text: str) -> str:
    """Lowercase and collapse text before exact hash comparisons.

    Example:
        `normalize_dedupe_text(" A\\nB ")`
    """
    return " ".join(text.lower().split())


def _dedupe_tokens(text: str) -> list[str]:
    tokens = TOKEN_PATTERN.findall(normalize_dedupe_text(text))
    return [token.strip("._-") for token in tokens if token.strip("._-")]


def find_url_duplicate(model: type[object], raw_url: str) -> object | None:
    """Find the first model row with a matching URL hash.

    Example:
        `find_url_duplicate(NormalizedDocument, url)`
    """
    hash_value = url_hash(raw_url)
    return model.objects.filter(url_hash=hash_value).first()


def _strip_trailing_path_slash(canonical_url: str) -> str:
    if "?" in canonical_url:
        path_part, query_part = canonical_url.split("?", 1)
        return f"{_strip_slash(path_part)}?{query_part}"
    return _strip_slash(canonical_url)


def _strip_slash(value: str) -> str:
    if value.count("/") <= 2:
        return value
    return value[:-1] if value.endswith("/") else value


def _weighted_simhash_value(token_counts: Counter[str]) -> int:
    weights = [0] * SIMHASH_BITS
    for token, count in token_counts.items():
        _add_token_weight(weights, token, count)
    return _weights_to_int(weights)


def _add_token_weight(weights: list[int], token: str, count: int) -> None:
    token_hash = int(hashlib.sha256(token.encode("utf-8")).hexdigest()[:16], 16)
    for bit_index in range(SIMHASH_BITS):
        bit_weight = count if token_hash & (1 << bit_index) else -count
        weights[bit_index] += bit_weight


def _weights_to_int(weights: list[int]) -> int:
    value = 0
    for bit_index, weight in enumerate(weights):
        if weight >= 0:
            value |= 1 << bit_index
    return value


def _sha256(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()
