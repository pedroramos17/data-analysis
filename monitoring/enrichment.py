"""Local deterministic document enrichment."""

import re
from collections import Counter
from dataclasses import dataclass
from decimal import Decimal
from urllib.parse import urlsplit

from django.utils import timezone

from monitoring.models import (
    CanonicalUrl,
    DocumentEnrichment,
    DocumentUrlReference,
    NormalizedDocument,
)
from monitoring.normalizers import canonicalize_url

ENRICHMENT_VERSION = 1
WORD_PATTERN = re.compile(r"[A-Za-z][A-Za-z0-9_-]{2,}")
HASHTAG_PATTERN = re.compile(r"#[A-Za-z0-9_]{2,}")
STOPWORDS = {"the", "and", "for", "with", "from", "that", "this", "into", "about"}
POSITIVE_WORDS = {"gain", "growth", "secure", "success", "improve", "positive"}
NEGATIVE_WORDS = {"risk", "attack", "loss", "fail", "breach", "negative", "crisis"}


@dataclass(frozen=True, slots=True)
class EnrichmentResult:
    """Computed local enrichment values for one document."""

    detected_language: str
    summary: str
    keywords: tuple[str, ...]
    hashtags: tuple[str, ...]
    sentiment_score: Decimal
    quality_flags: tuple[str, ...]


def enrich_document(document: NormalizedDocument, force: bool = False) -> bool:
    """Create or update local enrichment for a document.

    Example:
        `created_or_updated = enrich_document(document, force=True)`
    """
    existing = DocumentEnrichment.objects.filter(document=document).first()
    if existing is not None and not force:
        return False
    result = build_enrichment_result(document)
    DocumentEnrichment.objects.update_or_create(
        document=document,
        defaults=_enrichment_defaults(result),
    )
    upsert_document_url_reference(document)
    return True


def build_enrichment_result(document: NormalizedDocument) -> EnrichmentResult:
    """Build deterministic NLP metadata from document text.

    Example:
        `result = build_enrichment_result(document)`
    """
    text = _document_text(document)
    return EnrichmentResult(
        detected_language=detect_language(text, document.language),
        summary=summarize_text(text),
        keywords=extract_keywords(text),
        hashtags=extract_hashtags(text),
        sentiment_score=score_sentiment(text),
        quality_flags=detect_quality_flags(document, text),
    )


def detect_language(text: str, fallback: str = "") -> str:
    """Detect a coarse language code using local stopword hints.

    Example:
        `detect_language("the market is open")`
    """
    if fallback:
        return fallback.lower()
    lowered = text.lower()
    if any(word in lowered for word in (" el ", " la ", " que ", " para ")):
        return "es"
    if any(word in lowered for word in (" o ", " de ", " para ", " com ")):
        return "pt"
    return "en"


def summarize_text(text: str) -> str:
    """Return the first useful sentences as a compact summary.

    Example:
        `summarize_text("First. Second. Third.")`
    """
    sentences = [
        part.strip() for part in re.split(r"(?<=[.!?])\s+", text) if part.strip()
    ]
    summary = " ".join(sentences[:2])
    return summary[:500]


def extract_keywords(text: str, limit: int = 12) -> tuple[str, ...]:
    """Extract frequent non-stopword keywords.

    Example:
        `extract_keywords("security security market")`
    """
    words = [word.lower() for word in WORD_PATTERN.findall(text)]
    counts = Counter(word for word in words if word not in STOPWORDS)
    return tuple(word for word, _count in counts.most_common(limit))


def extract_hashtags(text: str) -> tuple[str, ...]:
    """Extract normalized hashtags.

    Example:
        `extract_hashtags("Watch #AI #AI")`
    """
    tags = [tag.lower() for tag in HASHTAG_PATTERN.findall(text)]
    return tuple(dict.fromkeys(tags))


def score_sentiment(text: str) -> Decimal:
    """Score simple lexicon sentiment from -1.00 to 1.00.

    Example:
        `score_sentiment("growth risk")`
    """
    words = set(word.lower() for word in WORD_PATTERN.findall(text))
    score = len(words & POSITIVE_WORDS) - len(words & NEGATIVE_WORDS)
    bounded = max(-1, min(1, score / 3))
    return Decimal(str(round(bounded, 2)))


def detect_quality_flags(document: NormalizedDocument, text: str) -> tuple[str, ...]:
    """Detect missing fields and spam-like repetition.

    Example:
        `detect_quality_flags(document, document.content)`
    """
    flags = []
    if not document.title.strip():
        flags.append("missing_title")
    if not document.published_at:
        flags.append("missing_published_at")
    if len(text) < 80:
        flags.append("short_content")
    if _has_repeated_tokens(text):
        flags.append("repeated_tokens")
    return tuple(flags)


def upsert_document_url_reference(document: NormalizedDocument) -> None:
    """Store canonical URL references for a document.

    Example:
        `upsert_document_url_reference(document)`
    """
    url = canonicalize_url(document.canonical_url)
    canonical_url, _created = CanonicalUrl.objects.get_or_create(
        canonical_url=url,
        defaults={"domain": _domain_from_url(url)},
    )
    canonical_url.last_seen_at = timezone.now()
    canonical_url.save(update_fields=["last_seen_at"])
    DocumentUrlReference.objects.get_or_create(
        document=document, canonical_url=canonical_url
    )


def _document_text(document: NormalizedDocument) -> str:
    return " ".join([document.title, document.content])


def _enrichment_defaults(result: EnrichmentResult) -> dict[str, object]:
    return {
        "detected_language": result.detected_language,
        "summary": result.summary,
        "keywords": list(result.keywords),
        "hashtags": list(result.hashtags),
        "sentiment_score": result.sentiment_score,
        "quality_flags": list(result.quality_flags),
        "enrichment_version": ENRICHMENT_VERSION,
    }


def _has_repeated_tokens(text: str) -> bool:
    words = [word.lower() for word in WORD_PATTERN.findall(text)]
    if len(words) < 12:
        return False
    most_common = Counter(words).most_common(1)[0][1]
    return most_common / len(words) > 0.35


def _domain_from_url(url: str) -> str:
    return urlsplit(url).netloc.lower().split(":", 1)[0]
