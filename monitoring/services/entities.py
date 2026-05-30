"""Pluggable entity extraction for article comparison."""

import re
from collections import Counter
from dataclasses import dataclass
from decimal import Decimal
from typing import Protocol

from monitoring.models import (
    ArticleEntityMention,
    CanonicalEntity,
    DocumentEntity,
    NormalizedDocument,
)

ENTITY_PATTERN = re.compile(
    r"\b[A-Z][A-Za-z0-9&.-]*(?:[ \t]+[A-Z][A-Za-z0-9&.-]*){0,4}\b"
)
STOP_ENTITIES = {"The", "And", "For", "This", "That"}


@dataclass(frozen=True, slots=True)
class EntityCandidate:
    """One backend-produced entity candidate."""

    text: str
    entity_type: str
    confidence: Decimal


class EntityExtractionBackend(Protocol):
    """Backend interface for entity extraction."""

    backend_name: str

    def extract(self, title: str, text: str) -> tuple[EntityCandidate, ...]:
        """Extract entity candidates from article text.

        Example:
            `backend.extract(article.title, article.text)`
        """


class LocalEntityBackend:
    """Regex-based local entity extraction."""

    backend_name = "local_heuristic"

    def extract(self, title: str, text: str) -> tuple[EntityCandidate, ...]:
        """Extract title-cased entity candidates.

        Example:
            `LocalEntityBackend().extract("OpenAI News", "OpenAI launched.")`
        """
        matches = ENTITY_PATTERN.findall(f"{title}\n{text}")
        names = tuple(dict.fromkeys(name.strip() for name in matches))
        return tuple(_candidate(name) for name in names if _is_useful(name))


def enrich_article_entities(
    article: NormalizedDocument,
    backend: EntityExtractionBackend | None = None,
) -> tuple[ArticleEntityMention, ...]:
    """Extract and persist entity mentions for an article.

    Example:
        `mentions = enrich_article_entities(article)`
    """
    extractor = backend or LocalEntityBackend()
    text = article.extracted_text or article.text or article.content
    candidates = extractor.extract(article.title, text)
    mentions = tuple(
        _upsert_mention(article, candidate, extractor.backend_name)
        for candidate in candidates
    )
    _sync_article_entity_names(article, mentions)
    return mentions


def article_entity_names(article: NormalizedDocument) -> set[str]:
    """Return normalized entity names for event scoring.

    Example:
        `article_entity_names(article)`
    """
    mentions = ArticleEntityMention.objects.filter(article=article).select_related(
        "entity"
    )
    names = {mention.entity.normalized_name for mention in mentions}
    return names or {str(name).lower() for name in article.entities}


def dominant_entity_names(
    articles: list[NormalizedDocument], limit: int = 10
) -> list[str]:
    """Return the most common entity names across articles.

    Example:
        `dominant_entity_names([article])`
    """
    counts = Counter(
        name for article in articles for name in article_entity_names(article)
    )
    return [name for name, _count in counts.most_common(limit)]


def _candidate(name: str) -> EntityCandidate:
    return EntityCandidate(name, "unknown", Decimal("1.00"))


def _is_useful(name: str) -> bool:
    return len(name) > 2 and name not in STOP_ENTITIES


def _upsert_mention(
    article: NormalizedDocument,
    candidate: EntityCandidate,
    backend_name: str,
) -> ArticleEntityMention:
    entity = _resolve_entity(candidate)
    mention, _created = ArticleEntityMention.objects.update_or_create(
        article=article,
        entity=entity,
        backend=backend_name,
        defaults=_mention_defaults(candidate),
    )
    _upsert_document_entity(article, entity, candidate.text)
    return mention


def _resolve_entity(candidate: EntityCandidate) -> CanonicalEntity:
    normalized_name = candidate.text.lower()
    entity, _created = CanonicalEntity.objects.get_or_create(
        normalized_name=normalized_name,
        defaults={"name": candidate.text, "entity_type": candidate.entity_type},
    )
    return entity


def _mention_defaults(candidate: EntityCandidate) -> dict[str, object]:
    return {
        "mention_text": candidate.text,
        "mention_count": 1,
        "confidence": candidate.confidence,
        "context": candidate.text,
    }


def _upsert_document_entity(
    article: NormalizedDocument,
    entity: CanonicalEntity,
    mention_text: str,
) -> None:
    DocumentEntity.objects.update_or_create(
        document=article,
        entity=entity,
        defaults={"mention_text": mention_text, "mention_count": 1},
    )


def _sync_article_entity_names(
    article: NormalizedDocument,
    mentions: tuple[ArticleEntityMention, ...],
) -> None:
    names = [mention.entity.name for mention in mentions]
    article.entities = names
    article.save(update_fields=["entities"])
