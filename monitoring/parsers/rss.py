"""RSS and Atom parsing helpers."""

import re
from html import unescape
from html.parser import HTMLParser
from collections.abc import Iterable
from typing_extensions import override
from xml.etree import ElementTree

from monitoring.contracts import ParsedRecord

MIN_SNIPPET_LENGTH = 24
SNIPPET_LIMIT = 400
BARE_AMPERSAND_PATTERN = re.compile(
    r"&(?!(?:#\d+|#x[0-9A-Fa-f]+|[A-Za-z][A-Za-z0-9]+);)"
)
INVALID_XML_CHAR_PATTERN = re.compile(r"[\x00-\x08\x0B\x0C\x0E-\x1F]")


class HtmlTextExtractor(HTMLParser):
    """Extract text from an HTML fragment.

    Example:
        `HtmlTextExtractor().feed("<p>Hello</p>")`
    """

    def __init__(self) -> None:
        super().__init__()
        self.parts: list[str] = []

    @override
    def handle_data(self, data: str) -> None:
        """Collect text data from an HTML fragment.

        Example:
            `extractor.handle_data("Hello")`
        """
        if data.strip():
            self.parts.append(data)

    def text(self) -> str:
        """Return normalized extracted text.

        Example:
            `text = extractor.text()`
        """
        return _normalize_text(" ".join(self.parts))


def parse_rss_records(
    xml_text: str, source_tags: tuple[str, ...] = ()
) -> list[ParsedRecord]:
    """Parse RSS or Atom XML into records.

    Example:
        `records = parse_rss_records(xml_text, ("security",))`
    """
    root = _parse_xml_root(xml_text)
    rss_items = root.findall(".//item")
    if rss_items:
        return _valid_records(_parse_rss_item(item, source_tags) for item in rss_items)
    return _valid_records(
        _parse_atom_entry(entry, source_tags) for entry in _atom_entries(root)
    )


def _parse_rss_item(item: ElementTree.Element, tags: tuple[str, ...]) -> ParsedRecord:
    link = _child_text(item, ("link",))
    title = _child_text(item, ("title",)) or link
    content = _digest_snippet(
        _first_text(item, ("description", "encoded", "summary", "content"))
    )
    published = _first_text(item, ("pubDate", "published", "updated", "date"))
    author = _first_text(item, ("author", "creator"))
    external_id = _first_text(item, ("guid", "id")) or link
    return ParsedRecord(link, title, content, external_id, author, published, tags=tags)


def _parse_atom_entry(
    entry: ElementTree.Element, tags: tuple[str, ...]
) -> ParsedRecord:
    link = _atom_link(entry)
    title = _child_text(entry, ("title",)) or link
    content = _digest_snippet(
        _first_text(entry, ("description", "encoded", "summary", "content"))
    )
    published = _first_text(entry, ("published", "updated"))
    author = _atom_author(entry)
    external_id = _child_text(entry, ("id",)) or link
    return ParsedRecord(link, title, content, external_id, author, published, tags=tags)


def _valid_records(records: Iterable[ParsedRecord]) -> list[ParsedRecord]:
    return [record for record in records if _has_digest_content(record)]


def _parse_xml_root(xml_text: str) -> ElementTree.Element:
    try:
        return ElementTree.fromstring(xml_text)
    except ElementTree.ParseError:
        return _parse_sanitized_xml_root(xml_text)


def _parse_sanitized_xml_root(xml_text: str) -> ElementTree.Element:
    try:
        return ElementTree.fromstring(_sanitize_xml_text(xml_text))
    except ElementTree.ParseError as error:
        excerpt = xml_text[:160]
        raise ValueError(
            f"Invalid RSS XML {excerpt!r}; expected RSS or Atom XML"
        ) from error


def _sanitize_xml_text(xml_text: str) -> str:
    stripped = _strip_leading_junk(xml_text)
    without_control_chars = INVALID_XML_CHAR_PATTERN.sub("", stripped)
    return BARE_AMPERSAND_PATTERN.sub("&amp;", without_control_chars)


def _strip_leading_junk(xml_text: str) -> str:
    first_angle = xml_text.find("<")
    if first_angle < 0:
        raise ValueError(f"Invalid RSS payload {xml_text[:80]!r}; expected XML")
    return xml_text[first_angle:]


def _has_digest_content(record: ParsedRecord) -> bool:
    if len(record.content) < MIN_SNIPPET_LENGTH:
        return False
    return (
        _normalize_text(record.content).lower() != _normalize_text(record.title).lower()
    )


def _digest_snippet(value: str) -> str:
    text = _strip_html(value)
    if len(text) <= SNIPPET_LIMIT:
        return text
    return text[:SNIPPET_LIMIT].rsplit(" ", 1)[0].rstrip()


def _strip_html(value: str) -> str:
    extractor = HtmlTextExtractor()
    extractor.feed(unescape(value))
    text = extractor.text()
    return text or _normalize_text(unescape(value))


def _atom_entries(root: ElementTree.Element) -> list[ElementTree.Element]:
    return [element for element in root.iter() if _local_name(element.tag) == "entry"]


def _atom_link(entry: ElementTree.Element) -> str:
    for child in entry:
        if _local_name(child.tag) == "link":
            return child.attrib.get("href", "")
    return ""


def _atom_author(entry: ElementTree.Element) -> str:
    for child in entry.iter():
        if _local_name(child.tag) == "name":
            return _clean_text(child.text)
    return ""


def _first_text(element: ElementTree.Element, names: tuple[str, ...]) -> str:
    for name in names:
        value = _child_text(element, (name,))
        if value:
            return value
    return ""


def _child_text(element: ElementTree.Element, names: tuple[str, ...]) -> str:
    for child in element.iter():
        if _local_name(child.tag) in names and child.text:
            return _clean_text(child.text)
    return ""


def _local_name(tag: str) -> str:
    if "}" not in tag:
        return tag
    return tag.rsplit("}", 1)[1]


def _clean_text(value: str | None) -> str:
    if value is None:
        return ""
    return _normalize_text(unescape(value))


def _normalize_text(value: str) -> str:
    return " ".join(value.split())
