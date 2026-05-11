"""Extractive summarization with a small TextRank implementation."""

from __future__ import annotations

from monitoring.nlp.preprocess import split_sentences, tokenize_words


def summarize_text(text: str, sentence_limit: int = 3) -> dict[str, object]:
    """Summarize text with token-overlap TextRank.

    Example:
        `summarize_text("One sentence. Another sentence.")`
    """
    sentences = split_sentences(text)
    if not sentences:
        return {"backend": "textrank", "text": "", "error": ""}
    ranked = _rank_sentences(sentences)
    selected = _select_sentences(sentences, ranked, sentence_limit)
    return {"backend": "textrank", "text": " ".join(selected), "error": ""}


def _rank_sentences(sentences: tuple[str, ...]) -> dict[int, float]:
    scores = {index: 1.0 for index in range(len(sentences))}
    similarities = _sentence_similarities(sentences)
    for _iteration in range(12):
        scores = _next_scores(scores, similarities)
    return scores


def _sentence_similarities(sentences: tuple[str, ...]) -> dict[tuple[int, int], float]:
    similarities: dict[tuple[int, int], float] = {}
    token_sets = [set(tokenize_words(sentence)) for sentence in sentences]
    for left_index, left_tokens in enumerate(token_sets):
        for right_index, right_tokens in enumerate(token_sets):
            if left_index != right_index:
                similarities[(left_index, right_index)] = _jaccard(
                    left_tokens, right_tokens
                )
    return similarities


def _next_scores(
    scores: dict[int, float],
    similarities: dict[tuple[int, int], float],
) -> dict[int, float]:
    next_scores: dict[int, float] = {}
    for index in scores:
        incoming = _incoming_score(index, scores, similarities)
        next_scores[index] = 0.15 + 0.85 * incoming
    return next_scores


def _incoming_score(
    index: int,
    scores: dict[int, float],
    similarities: dict[tuple[int, int], float],
) -> float:
    total = 0.0
    for other_index, other_score in scores.items():
        if other_index != index:
            total += other_score * similarities.get((other_index, index), 0.0)
    return total


def _select_sentences(
    sentences: tuple[str, ...],
    scores: dict[int, float],
    sentence_limit: int,
) -> tuple[str, ...]:
    ranked_indexes = sorted(scores, key=scores.get, reverse=True)[:sentence_limit]
    selected_indexes = sorted(ranked_indexes)
    return tuple(sentences[index] for index in selected_indexes)


def _jaccard(left_tokens: set[str], right_tokens: set[str]) -> float:
    if not left_tokens or not right_tokens:
        return 0.0
    return len(left_tokens & right_tokens) / len(left_tokens | right_tokens)
