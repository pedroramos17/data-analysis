"""Source adapters that connect fetchers to parsers."""

from django.conf import settings

from monitoring.contracts import (
    FetchedRecord,
    FetchRequest,
    FetchResult,
    ParsedRecord,
    PublicFetcher,
    SourceAdapter,
)
from monitoring.fetchers.browser import HeadlessBrowserFetcher
from monitoring.fetchers.http import HttpFetcher
from monitoring.models import Source
from monitoring.parsers.api import parse_api_records
from monitoring.parsers.arxiv import parse_arxiv_api_records
from monitoring.parsers.html import parse_html_document
from monitoring.parsers.rss import parse_rss_records
from monitoring.parsers.sitemap import parse_sitemap_urls


class RssSourceAdapter:
    """Fetch and parse an RSS or Atom source.

    Example:
        `RssSourceAdapter(source, fetcher).fetch_records(limit=10)`
    """

    def __init__(self, source: Source, fetcher: PublicFetcher) -> None:
        self.source = source
        self.fetcher = fetcher

    def fetch_records(self, limit: int | None = None) -> list[FetchedRecord]:
        """Return parsed RSS records for the source.

        Example:
            `records = adapter.fetch_records(limit=20)`
        """
        result = self.fetcher.fetch(_request_for(self.source))
        records = parse_rss_records(result.body, _source_tags(self.source))
        return _fetched_records(result, records[:limit])


class HtmlSourceAdapter:
    """Fetch and parse one HTML source page.

    Example:
        `HtmlSourceAdapter(source, fetcher).fetch_records()`
    """

    def __init__(self, source: Source, fetcher: PublicFetcher) -> None:
        self.source = source
        self.fetcher = fetcher

    def fetch_records(self, limit: int | None = None) -> list[FetchedRecord]:
        """Return the parsed HTML record.

        Example:
            `records = adapter.fetch_records()`
        """
        result = self.fetcher.fetch(_request_for(self.source))
        record = parse_html_document(result.body, result.url, _source_tags(self.source))
        return _fetched_records(result, [record][:limit])


class SitemapSourceAdapter:
    """Fetch a sitemap and parse linked HTML pages.

    Example:
        `SitemapSourceAdapter(source, http_fetcher, page_fetcher).fetch_records(25)`
    """

    def __init__(
        self,
        source: Source,
        sitemap_fetcher: PublicFetcher,
        page_fetcher: PublicFetcher,
    ) -> None:
        self.source = source
        self.sitemap_fetcher = sitemap_fetcher
        self.page_fetcher = page_fetcher

    def fetch_records(self, limit: int | None = None) -> list[FetchedRecord]:
        """Return parsed records from URLs listed in the sitemap.

        Example:
            `records = adapter.fetch_records(limit=10)`
        """
        sitemap_result = self.sitemap_fetcher.fetch(_request_for(self.source))
        urls = parse_sitemap_urls(sitemap_result.body)[:limit]
        return [self._fetched_html_record(url) for url in urls]

    def _fetched_html_record(self, url: str) -> FetchedRecord:
        result = self.page_fetcher.fetch(_request_for(self.source, url))
        record = parse_html_document(result.body, result.url, _source_tags(self.source))
        return FetchedRecord(result, record)


class ApiSourceAdapter:
    """Fetch and parse an approved public JSON API source.

    Example:
        `ApiSourceAdapter(source, fetcher).fetch_records(limit=10)`
    """

    def __init__(self, source: Source, fetcher: PublicFetcher) -> None:
        self.source = source
        self.fetcher = fetcher

    def fetch_records(self, limit: int | None = None) -> list[FetchedRecord]:
        """Return parsed API records for an approved public endpoint.

        Example:
            `records = adapter.fetch_records(limit=25)`
        """
        result = self.fetcher.fetch(_request_for(self.source))
        records = _parse_api_result(self.source, result)
        return _fetched_records(result, records[:limit])


def build_source_adapter(source: Source) -> SourceAdapter:
    """Build the right adapter for a source registry entry.

    Example:
        `adapter = build_source_adapter(source)`
    """
    http_fetcher = HttpFetcher()
    page_fetcher = _page_fetcher_for(source)
    if source.source_type == Source.SourceType.RSS:
        return RssSourceAdapter(source, http_fetcher)
    if source.source_type == Source.SourceType.HTML:
        return HtmlSourceAdapter(source, page_fetcher)
    if source.source_type == Source.SourceType.SITEMAP:
        return SitemapSourceAdapter(source, http_fetcher, page_fetcher)
    if source.source_type == Source.SourceType.API:
        return ApiSourceAdapter(source, http_fetcher)
    raise ValueError(
        f"Invalid source type {source.source_type!r}; expected rss, html, sitemap, or api"
    )


def _page_fetcher_for(source: Source) -> PublicFetcher:
    if source.fetch_method == Source.FetchMethod.BROWSER:
        return HeadlessBrowserFetcher()
    return HttpFetcher()


def _request_for(source: Source, url: str | None = None) -> FetchRequest:
    return FetchRequest(
        source_id=source.id or 0,
        url=url or source.url,
        user_agent=settings.MONITOR_USER_AGENT,
        rate_limit_seconds=float(source.rate_limit_seconds),
        respect_robots=_respect_robots_for(source),
    )


def _respect_robots_for(source: Source) -> bool:
    return source.source_type != Source.SourceType.RSS


def _source_tags(source: Source) -> tuple[str, ...]:
    return tuple(str(tag) for tag in source.tags)


def _fetched_records(
    result: FetchResult,
    records: list[ParsedRecord],
) -> list[FetchedRecord]:
    return [FetchedRecord(result, record) for record in records]


def _parse_api_result(source: Source, result: FetchResult) -> list[ParsedRecord]:
    if "export.arxiv.org/api/query" in source.url:
        return parse_arxiv_api_records(result.body, _source_tags(source))
    return parse_api_records(result.body, _source_tags(source))
