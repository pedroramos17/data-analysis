"""Typed contracts shared by fetchers, parsers, and storage."""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Mapping, Protocol


@dataclass(frozen=True, slots=True)
class FetchRequest:
    """A single public URL request.

    Example:
        `FetchRequest(source_id=1, url="https://example.com/feed.xml")`
    """

    source_id: int
    url: str
    user_agent: str
    timeout_seconds: int = 20
    rate_limit_seconds: float = 0.0
    respect_robots: bool = True
    headers: Mapping[str, str] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class FetchResult:
    """A fetched HTTP or browser response body.

    Example:
        `FetchResult(url=url, status_code=200, body="<html></html>")`
    """

    url: str
    status_code: int
    body: str
    content_type: str
    headers: Mapping[str, str]
    fetched_at: datetime


@dataclass(frozen=True, slots=True)
class ParsedRecord:
    """A source record before canonical normalization.

    Example:
        `ParsedRecord(url=url, title="Advisory", content="...")`
    """

    url: str
    title: str
    content: str
    external_id: str = ""
    author: str = ""
    published_text: str = ""
    language: str = ""
    tags: tuple[str, ...] = ()
    metadata: Mapping[str, str] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class NormalizedRecord:
    """A normalized document ready for database storage.

    Example:
        `NormalizedRecord(canonical_url=url, title="Title", dedupe_hash="...")`
    """

    canonical_url: str
    title: str
    author: str
    published_at: datetime | None
    language: str
    content: str
    entities: tuple[str, ...]
    tags: tuple[str, ...]
    dedupe_hash: str
    metadata: Mapping[str, str] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class FetchedRecord:
    """A parsed record paired with the response that produced it.

    Example:
        `FetchedRecord(fetch_result=response, parsed_record=record)`
    """

    fetch_result: FetchResult
    parsed_record: ParsedRecord


@dataclass(frozen=True, slots=True)
class IngestionSummary:
    """A compact ingestion outcome for commands and logs.

    Example:
        `IngestionSummary(source_id=1, parsed_count=5, created_count=2)`
    """

    source_id: int
    parsed_count: int
    raw_created_count: int
    document_created_count: int
    duplicate_count: int
    failed_count: int


class PublicFetcher(Protocol):
    """Fetch public URLs without bypassing access controls.

    Example:
        `fetcher.fetch(FetchRequest(source_id=1, url=url, user_agent=ua))`
    """

    def fetch(self, request: FetchRequest) -> FetchResult:
        """Fetch one public URL.

        Example:
            `result = fetcher.fetch(request)`
        """


class SourceAdapter(Protocol):
    """Convert a source into fetched parsed records.

    Example:
        `adapter.fetch_records(limit=10)`
    """

    def fetch_records(self, limit: int | None = None) -> list[FetchedRecord]:
        """Fetch and parse source records.

        Example:
            `records = adapter.fetch_records(limit=20)`
        """
