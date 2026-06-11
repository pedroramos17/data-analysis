"""Candidate entity extraction provider interface and local heuristic extractor."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Protocol


@dataclass(frozen=True)
class EntityMentionCandidate:
    """A candidate entity mention with text span and confidence."""

    text: str
    entity_type: str
    char_start: int
    char_end: int
    confidence: Decimal = Decimal("0.70")
    extractor_name: str = "heuristic_entity_extractor"
    extractor_version: str = "1"
    metadata_json: dict[str, object] = field(default_factory=dict)


class EntityExtractor(Protocol):
    """Provider contract for entity mention extraction."""

    def extract(self, text: str) -> list[EntityMentionCandidate]:
        """Return candidate entity mentions for text."""


TICKER_PATTERN = re.compile(r"(?<![A-Za-z0-9])(?:([A-Z]{2,8})[:.])?([A-Z]{1,6})(?![A-Za-z0-9])")
NAME_PATTERN = re.compile(
    r"\b[A-Z][A-Za-z0-9&.-]+(?:\s+[A-Z][A-Za-z0-9&.-]+){0,4}\b"
)
COMMON_UPPERCASE_WORDS = frozenset(
    {
        "CEO",
        "CFO",
        "COO",
        "EPS",
        "GDP",
        "IPO",
        "M&A",
        "SEC",
        "USD",
    }
)
COMMON_TITLE_WORDS = frozenset(
    {
        "A",
        "An",
        "And",
        "As",
        "At",
        "But",
        "For",
        "From",
        "If",
        "In",
        "Into",
        "Of",
        "On",
        "Or",
        "The",
        "To",
        "With",
    }
)
REGULATOR_NAMES = frozenset(
    {
        "Central Bank",
        "CVM",
        "ECB",
        "Fed",
        "Federal Reserve",
        "SEC",
    }
)
COMPANY_SUFFIXES = ("Corp", "Corporation", "Inc", "Limited", "Ltd", "Platforms", "SA", "S.A.")


class HeuristicEntityExtractor:
    """Dependency-light fallback extractor for financial documents."""

    name = "heuristic_entity_extractor"
    version = "1"

    def extract(self, text: str) -> list[EntityMentionCandidate]:
        """Extract ticker-like identifiers and title-cased names."""
        candidates = [*_ticker_candidates(text), *_name_candidates(text)]
        return _dedupe_candidates(candidates)


def extract_candidates(text: str, extractor: EntityExtractor | None = None) -> list[EntityMentionCandidate]:
    """Extract entity mentions using a provider or the local heuristic fallback."""
    active_extractor = extractor or HeuristicEntityExtractor()
    return active_extractor.extract(text)


def _ticker_candidates(text: str) -> list[EntityMentionCandidate]:
    candidates: list[EntityMentionCandidate] = []
    for match in TICKER_PATTERN.finditer(text):
        namespace, value = match.groups()
        if value in COMMON_UPPERCASE_WORDS:
            continue
        if len(value) == 1 and not namespace:
            continue
        metadata: dict[str, object] = {"identifier_type": "ticker"}
        if namespace:
            metadata["namespace"] = namespace
        candidates.append(
            EntityMentionCandidate(
                text=value,
                entity_type="Security",
                char_start=match.start(2),
                char_end=match.end(2),
                confidence=Decimal("0.92") if namespace else Decimal("0.82"),
                metadata_json=metadata,
            )
        )
    return candidates


def _name_candidates(text: str) -> list[EntityMentionCandidate]:
    candidates: list[EntityMentionCandidate] = []
    for match in NAME_PATTERN.finditer(text):
        value = match.group(0).strip()
        if not _useful_name(value):
            continue
        candidates.append(
            EntityMentionCandidate(
                text=value,
                entity_type=_guess_entity_type(value),
                char_start=match.start(),
                char_end=match.end(),
                confidence=Decimal("0.72"),
            )
        )
    return candidates


def _useful_name(value: str) -> bool:
    if len(value) <= 2:
        return False
    if value in COMMON_TITLE_WORDS:
        return False
    first_word = value.split()[0]
    if first_word in COMMON_TITLE_WORDS and len(value.split()) == 1:
        return False
    if value.isupper() and value in COMMON_UPPERCASE_WORDS:
        return False
    return True


def _guess_entity_type(value: str) -> str:
    if value in REGULATOR_NAMES:
        return "Regulator"
    if value.isupper() and len(value) <= 6:
        return "Security"
    if value.endswith(COMPANY_SUFFIXES):
        return "Company"
    return "Company"


def _dedupe_candidates(candidates: list[EntityMentionCandidate]) -> list[EntityMentionCandidate]:
    by_span: dict[tuple[int, int, str], EntityMentionCandidate] = {}
    for candidate in candidates:
        key = (candidate.char_start, candidate.char_end, candidate.text)
        current = by_span.get(key)
        if current is None or candidate.confidence > current.confidence:
            by_span[key] = candidate
    return sorted(by_span.values(), key=lambda item: (item.char_start, item.char_end))
