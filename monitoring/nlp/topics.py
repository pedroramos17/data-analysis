"""CPU-first topic classification baselines."""

from __future__ import annotations

from collections.abc import Sequence

from monitoring.nlp.preprocess import tokenize_words

SEED_TOPICS = {
    "security": "security breach attack advisory malware vulnerability defense",
    "markets": "market earnings stocks rates inflation asset liquidity",
    "technology": "technology ai software cloud chip semiconductor platform",
    "science": "research paper arxiv experiment climate health space",
    "politics": "government election policy regulation parliament white house",
    "climate": "climate weather ocean emissions energy carbon storm noaa",
}


def classify_topics(text: str, limit: int = 3) -> dict[str, object]:
    """Classify topics with TF-IDF similarity when scikit-learn is installed.

    Example:
        `classify_topics("malware advisory released")`
    """
    sklearn_result = _classify_with_sklearn(text, limit)
    if not sklearn_result["error"]:
        return sklearn_result
    fallback_items = _keyword_topic_scores(text, limit)
    sklearn_result["items"] = fallback_items
    sklearn_result["backend"] = "keyword-fallback"
    return sklearn_result


def train_topic_classifier(texts: Sequence[str], labels: Sequence[str]) -> object:
    """Train a small TF-IDF and LogisticRegression topic classifier.

    Example:
        `model = train_topic_classifier(["breach report"], ["security"])`
    """
    if len(texts) != len(labels):
        raise ValueError(f"Invalid training rows {len(texts)}; expected labels match")
    return _fit_logistic_regression(texts, labels)


def _classify_with_sklearn(text: str, limit: int) -> dict[str, object]:
    try:
        from sklearn.feature_extraction.text import TfidfVectorizer
        from sklearn.metrics.pairwise import cosine_similarity
    except ImportError as error:
        return _topic_error("sklearn", error)
    labels = tuple(SEED_TOPICS.keys())
    corpus = (text, *tuple(SEED_TOPICS.values()))
    matrix = TfidfVectorizer().fit_transform(corpus)
    scores = cosine_similarity(matrix[0:1], matrix[1:]).flatten()
    return _topic_payload(labels, scores, limit, "sklearn-tfidf")


def _fit_logistic_regression(texts: Sequence[str], labels: Sequence[str]) -> object:
    from sklearn.feature_extraction.text import TfidfVectorizer
    from sklearn.linear_model import LogisticRegression
    from sklearn.pipeline import Pipeline

    classifier = Pipeline(
        [("tfidf", TfidfVectorizer()), ("clf", LogisticRegression(max_iter=200))]
    )
    return classifier.fit(texts, labels)


def _keyword_topic_scores(text: str, limit: int) -> list[dict[str, object]]:
    tokens = set(tokenize_words(text))
    scored = [
        (_seed_overlap(tokens, label, seed), label)
        for label, seed in SEED_TOPICS.items()
    ]
    ranked = sorted(scored, reverse=True)[:limit]
    return [
        {"label": label, "score": round(score, 4)}
        for score, label in ranked
        if score > 0
    ]


def _seed_overlap(tokens: set[str], label: str, seed: str) -> float:
    seed_tokens = set(tokenize_words(f"{label} {seed}"))
    if not tokens:
        return 0.0
    return len(tokens & seed_tokens) / max(1, len(seed_tokens))


def _topic_payload(
    labels: tuple[str, ...],
    scores: Sequence[float],
    limit: int,
    backend: str,
) -> dict[str, object]:
    scored = [(float(score), labels[index]) for index, score in enumerate(scores)]
    ranked = sorted(scored, reverse=True)[:limit]
    items = [{"label": label, "score": round(score, 4)} for score, label in ranked]
    return {"backend": backend, "items": items, "error": ""}


def _topic_error(backend: str, error: ImportError) -> dict[str, object]:
    message = f"{backend} unavailable for topics; expected installed package: {error}"
    return {"backend": f"{backend}-unavailable", "items": [], "error": message}
