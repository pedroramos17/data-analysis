"""HTML metadata and article-text parsing helpers."""

from html.parser import HTMLParser
from typing_extensions import override

from monitoring.contracts import ParsedRecord


class HtmlDocumentParser(HTMLParser):
    """Collect useful metadata and paragraph text from HTML.

    Example:
        `parser = HtmlDocumentParser(); parser.feed(html)`
    """

    def __init__(self) -> None:
        super().__init__()
        self.title_parts: list[str] = []
        self.paragraphs: list[str] = []
        self.metadata: dict[str, str] = {}
        self.language = ""
        self._capture_title = False
        self._capture_paragraph = False

    @override
    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        """Capture title, paragraph, meta, and language boundaries.

        Example:
            `parser.handle_starttag("title", [])`
        """
        attributes = _attrs_to_map(attrs)
        if tag == "title":
            self._capture_title = True
        if tag == "p":
            self._capture_paragraph = True
        self._capture_metadata(tag, attributes)
        self._capture_language(tag, attributes)

    @override
    def handle_endtag(self, tag: str) -> None:
        """Stop text capture at closing title and paragraph tags.

        Example:
            `parser.handle_endtag("p")`
        """
        if tag == "title":
            self._capture_title = False
        if tag == "p":
            self._capture_paragraph = False

    @override
    def handle_data(self, data: str) -> None:
        """Append captured title or paragraph text.

        Example:
            `parser.handle_data("Article title")`
        """
        text = " ".join(data.split())
        if self._capture_title and text:
            self.title_parts.append(text)
        if self._capture_paragraph and text:
            self.paragraphs.append(text)

    def _capture_metadata(self, tag: str, attrs: dict[str, str]) -> None:
        if tag == "meta":
            self._capture_meta_tag(attrs)
        if tag == "link" and attrs.get("rel") == "canonical":
            self.metadata["canonical"] = attrs.get("href", "")

    def _capture_meta_tag(self, attrs: dict[str, str]) -> None:
        key = attrs.get("name") or attrs.get("property")
        content = attrs.get("content", "")
        if key and content:
            self.metadata[key.lower()] = content

    def _capture_language(self, tag: str, attrs: dict[str, str]) -> None:
        if tag == "html" and attrs.get("lang"):
            self.language = attrs["lang"]


def parse_html_document(
    html_text: str,
    url: str,
    source_tags: tuple[str, ...] = (),
) -> ParsedRecord:
    """Parse one HTML page into a record.

    Example:
        `record = parse_html_document(html_text, "https://example.com/post")`
    """
    parser = HtmlDocumentParser()
    parser.feed(html_text)
    title = _html_title(parser) or url
    content = _html_content(parser)
    return ParsedRecord(
        url=_canonical_from_html(parser, url),
        title=title,
        content=content,
        external_id=_canonical_from_html(parser, url),
        author=_html_author(parser),
        published_text=_html_published(parser),
        language=parser.language,
        tags=source_tags,
        metadata=parser.metadata,
    )


def _attrs_to_map(attrs: list[tuple[str, str | None]]) -> dict[str, str]:
    return {key.lower(): value or "" for key, value in attrs}


def _html_title(parser: HtmlDocumentParser) -> str:
    return _first_metadata(parser, ("og:title", "twitter:title")) or " ".join(
        parser.title_parts
    )


def _html_content(parser: HtmlDocumentParser) -> str:
    body = "\n".join(parser.paragraphs)
    return body or _first_metadata(parser, ("description", "og:description"))


def _html_author(parser: HtmlDocumentParser) -> str:
    return _first_metadata(parser, ("author", "article:author"))


def _html_published(parser: HtmlDocumentParser) -> str:
    return _first_metadata(
        parser,
        ("article:published_time", "date", "pubdate", "publishdate"),
    )


def _canonical_from_html(parser: HtmlDocumentParser, fallback_url: str) -> str:
    return (
        parser.metadata.get("canonical")
        or parser.metadata.get("og:url")
        or fallback_url
    )


def _first_metadata(parser: HtmlDocumentParser, keys: tuple[str, ...]) -> str:
    for key in keys:
        value = parser.metadata.get(key, "")
        if value:
            return value
    return ""
