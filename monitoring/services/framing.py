"""Explainable local framing features for article comparison."""

import re
from dataclasses import dataclass
from typing import Protocol

from monitoring.models import FrameFeature, NormalizedDocument

WORD_PATTERN = re.compile(r"[A-Za-z][A-Za-z0-9_-]{2,}")
QUOTE_PATTERN = re.compile(r'"[^"]+"|“[^”]+”')
ATTRIBUTION_WORDS = {"said", "according", "reported", "claimed", "announced"}
MODAL_WORDS = {"may", "might", "could", "would", "should", "allegedly"}
POSITIVE_WORDS = {"gain", "growth", "secure", "success", "improve", "benefit"}
NEGATIVE_WORDS = {"risk", "attack", "loss", "fail", "breach", "crisis"}
LOADED_WORDS = {"shocking", "secret", "explosive", "scandal", "disaster"}


@dataclass(frozen=True, slots=True)
class FrameFeatureResult:
    """One backend-produced framing feature."""

    feature_type: str
    value: float
    evidence: dict[str, object]


class FramingBackend(Protocol):
    """Backend interface for framing feature extraction."""

    backend_name: str

    def extract(self, text: str) -> tuple[FrameFeatureResult, ...]:
        """Extract explainable framing features.

        Example:
            `backend.extract("Officials said risks may rise.")`
        """


class LocalFramingBackend:
    """Lexicon-based framing feature extraction."""

    backend_name = "local_heuristic"

    def extract(self, text: str) -> tuple[FrameFeatureResult, ...]:
        """Extract local, deterministic framing features.

        Example:
            `LocalFramingBackend().extract("Officials said risks may rise.")`
        """
        words = [word.lower() for word in WORD_PATTERN.findall(text)]
        return (
            _density_feature("quote_density", len(QUOTE_PATTERN.findall(text)), words),
            _count_feature("attribution_count", words, ATTRIBUTION_WORDS),
            _count_feature("modal_count", words, MODAL_WORDS),
            _sentiment_feature(words),
            _count_feature("loaded_language_count", words, LOADED_WORDS),
        )


def extract_article_frame_features(
    article: NormalizedDocument,
    backend: FramingBackend | None = None,
) -> tuple[FrameFeature, ...]:
    """Extract and persist explainable framing features.

    Example:
        `features = extract_article_frame_features(article)`
    """
    extractor = backend or LocalFramingBackend()
    text = " ".join(
        [article.title, article.extracted_text or article.text or article.content]
    )
    results = extractor.extract(text)
    return tuple(
        _upsert_feature(article, result, extractor.backend_name) for result in results
    )


def article_frame_features(article: NormalizedDocument) -> dict[str, float]:
    """Return persisted frame features as a dictionary.

    Example:
        `article_frame_features(article)`
    """
    features = FrameFeature.objects.filter(article=article)
    return {feature.feature_type: float(feature.value) for feature in features}


def _density_feature(
    feature_type: str,
    count: int,
    words: list[str],
) -> FrameFeatureResult:
    denominator = max(1, len(words))
    return FrameFeatureResult(feature_type, round(count / denominator, 4), {})


def _count_feature(
    feature_type: str,
    words: list[str],
    lexicon: set[str],
) -> FrameFeatureResult:
    matches = [word for word in words if word in lexicon]
    return FrameFeatureResult(feature_type, float(len(matches)), {"matches": matches})


def _sentiment_feature(words: list[str]) -> FrameFeatureResult:
    score = len(set(words) & POSITIVE_WORDS) - len(set(words) & NEGATIVE_WORDS)
    return FrameFeatureResult("sentiment_score", float(score), {})


def _upsert_feature(
    article: NormalizedDocument,
    result: FrameFeatureResult,
    backend_name: str,
) -> FrameFeature:
    feature, _created = FrameFeature.objects.update_or_create(
        article=article,
        feature_type=result.feature_type,
        backend=backend_name,
        defaults={"value": result.value, "evidence": result.evidence},
    )
    return feature
