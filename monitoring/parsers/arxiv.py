"""Parser for arXiv API Atom responses."""

from xml.etree import ElementTree

from monitoring.contracts import ParsedRecord
from monitoring.parsers.rss import _digest_snippet

ATOM_NS = "{http://www.w3.org/2005/Atom}"
ARXIV_NS = "{http://arxiv.org/schemas/atom}"


def parse_arxiv_api_records(
    xml_text: str,
    source_tags: tuple[str, ...] = (),
) -> list[ParsedRecord]:
    """Parse arXiv API Atom XML into normalized parser records.

    Example:
        `records = parse_arxiv_api_records(xml_text, ("science",))`
    """
    root = ElementTree.fromstring(xml_text)
    entries = root.findall(f"{ATOM_NS}entry")
    return [_parse_entry(entry, source_tags) for entry in entries]


def _parse_entry(entry: ElementTree.Element, tags: tuple[str, ...]) -> ParsedRecord:
    title = _text(entry, f"{ATOM_NS}title")
    summary = _digest_snippet(_text(entry, f"{ATOM_NS}summary"))
    entry_id = _text(entry, f"{ATOM_NS}id")
    authors = ", ".join(_author_names(entry))
    published = _text(entry, f"{ATOM_NS}published")
    categories = _categories(entry)
    metadata = _metadata(entry, entry_id, categories)
    return ParsedRecord(
        url=_abstract_url(entry, entry_id),
        title=title,
        content=summary,
        external_id=_arxiv_identifier(entry_id),
        author=authors,
        published_text=published,
        tags=tags + categories,
        metadata=metadata,
    )


def _metadata(
    entry: ElementTree.Element,
    entry_id: str,
    categories: tuple[str, ...],
) -> dict[str, str]:
    return {
        "arxiv_id": _arxiv_identifier(entry_id),
        "updated": _text(entry, f"{ATOM_NS}updated"),
        "doi": _text(entry, f"{ARXIV_NS}doi"),
        "journal_ref": _text(entry, f"{ARXIV_NS}journal_ref"),
        "comment": _text(entry, f"{ARXIV_NS}comment"),
        "categories": ",".join(categories),
        "pdf_url": _link(entry, "pdf"),
    }


def _author_names(entry: ElementTree.Element) -> tuple[str, ...]:
    names = []
    for author in entry.findall(f"{ATOM_NS}author"):
        name = author.findtext(f"{ATOM_NS}name", default="")
        if name.strip():
            names.append(name.strip())
    return tuple(names)


def _categories(entry: ElementTree.Element) -> tuple[str, ...]:
    values = []
    for category in entry.findall(f"{ATOM_NS}category"):
        term = category.attrib.get("term", "").strip()
        if term:
            values.append(term)
    return tuple(values)


def _abstract_url(entry: ElementTree.Element, entry_id: str) -> str:
    alternate = _link(entry, "alternate")
    return alternate or entry_id


def _link(entry: ElementTree.Element, rel: str) -> str:
    for link in entry.findall(f"{ATOM_NS}link"):
        if link.attrib.get("rel") == rel or link.attrib.get("title") == rel:
            return link.attrib.get("href", "")
    return ""


def _text(entry: ElementTree.Element, path: str) -> str:
    return " ".join(entry.findtext(path, default="").split())


def _arxiv_identifier(entry_id: str) -> str:
    if not entry_id:
        return ""
    return entry_id.rstrip("/").rsplit("/", 1)[-1]
