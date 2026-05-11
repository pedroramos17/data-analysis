"""Sentiment scoring through VADER with a local lexicon fallback."""

from __future__ import annotations

from monitoring.nlp.preprocess import tokenize_words

POSITIVE_WORDS = {"gain", "growth", "improve", "positive", "secure", "success"}
NEGATIVE_WORDS = {"attack", "breach", "crisis", "fail", "loss", "negative", "risk"}


def score_sentiment(text: str) -> dict[str, object]:
    """Score sentiment with VADER when available.

    Example:
        `score_sentiment("secure growth but breach risk")`
    """
    vader_result = _score_with_vader(text)
    if not vader_result["error"]:
        return vader_result
    fallback_score = _score_with_lexicon(text)
    vader_result.update(_sentiment_payload(fallback_score, "lexicon-fallback"))
    return vader_result


def _score_with_vader(text: str) -> dict[str, object]:
    try:
        from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer
    except ImportError as error:
        return _sentiment_error("vader", error)
    analyzer = SentimentIntensityAnalyzer()
    compound = analyzer.polarity_scores(text)["compound"]
    return _sentiment_payload(float(compound), "vader")


def _score_with_lexicon(text: str) -> float:
    tokens = set(tokenize_words(text))
    raw_score = len(tokens & POSITIVE_WORDS) - len(tokens & NEGATIVE_WORDS)
    bounded = max(-1.0, min(1.0, raw_score / 3))
    return round(bounded, 3)


def _sentiment_payload(score: float, backend: str) -> dict[str, object]:
    label = _sentiment_label(score)
    payload = {"backend": backend, "score": score, "label": label, "error": ""}
    return payload


def _sentiment_label(score: float) -> str:
    if score >= 0.15:
        return "positive"
    if score <= -0.15:
        return "negative"
    return "neutral"


def _sentiment_error(backend: str, error: ImportError) -> dict[str, object]:
    message = (
        f"{backend} unavailable for sentiment; expected installed package: {error}"
    )
    return {
        "backend": f"{backend}-unavailable",
        "score": 0.0,
        "label": "neutral",
        "error": message,
    }
