"""Pluggable claim extraction for comparison snapshots."""

import re
from dataclasses import dataclass
from decimal import Decimal
from typing import Protocol

from monitoring.models import Claim, NormalizedDocument

SENTENCE_PATTERN = re.compile(r"(?<=[.!?])\s+")
MIN_CLAIM_LENGTH = 24


@dataclass(frozen=True, slots=True)
class ClaimCandidate:
    """One backend-produced claim candidate."""

    text: str
    claim_type: str
    confidence: Decimal


class ClaimExtractionBackend(Protocol):
    """Backend interface for extracting article claims."""

    backend_name: str

    def extract(self, title: str, text: str) -> tuple[ClaimCandidate, ...]:
        """Extract claim candidates from article text.

        Example:
            `backend.extract(article.title, article.text)`
        """


class LocalClaimBackend:
    """Sentence-based local claim extraction."""

    backend_name = "local_heuristic"

    def extract(self, title: str, text: str) -> tuple[ClaimCandidate, ...]:
        """Extract sentence-level claim candidates.

        Example:
            `LocalClaimBackend().extract("Title", "A useful sentence.")`
        """
        sentences = _candidate_sentences(title, text)
        return tuple(_claim_candidate(sentence) for sentence in sentences)


def extract_article_claims(
    article: NormalizedDocument,
    backend: ClaimExtractionBackend | None = None,
) -> tuple[Claim, ...]:
    """Extract and persist claim candidates for one article.

    Example:
        `claims = extract_article_claims(article)`
    """
    extractor = backend or LocalClaimBackend()
    text = article.extracted_text or article.text or article.content
    candidates = extractor.extract(article.title, text)
    return tuple(
        _upsert_claim(article, candidate, extractor.backend_name)
        for candidate in candidates
    )


def normalize_claim_text(text: str) -> str:
    """Normalize a claim for exact MVP clustering.

    Example:
        `normalize_claim_text(" A claim. ")`
    """
    return " ".join(text.lower().strip(" .!?").split())[:500]


def _candidate_sentences(title: str, text: str) -> tuple[str, ...]:
    basis = text or title
    sentences = [sentence.strip() for sentence in SENTENCE_PATTERN.split(basis)]
    useful = [sentence for sentence in sentences if len(sentence) >= MIN_CLAIM_LENGTH]
    return tuple(dict.fromkeys(useful))


def _claim_candidate(sentence: str) -> ClaimCandidate:
    return ClaimCandidate(sentence, "statement", Decimal("1.00"))


def _upsert_claim(
    article: NormalizedDocument,
    candidate: ClaimCandidate,
    backend_name: str,
) -> Claim:
    claim, _created = Claim.objects.update_or_create(
        article=article,
        normalized_claim=normalize_claim_text(candidate.text),
        backend=backend_name,
        defaults=_claim_defaults(candidate),
    )
    return claim


def _claim_defaults(candidate: ClaimCandidate) -> dict[str, object]:
    return {
        "claim_text": candidate.text,
        "claim_type": candidate.claim_type,
        "confidence": candidate.confidence,
    }
