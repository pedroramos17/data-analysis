"""Sitemap parsing helpers."""

from xml.etree import ElementTree


def parse_sitemap_urls(xml_text: str) -> list[str]:
    """Extract URLs from a sitemap XML document.

    Example:
        `urls = parse_sitemap_urls(xml_text)`
    """
    root = ElementTree.fromstring(xml_text)
    return [_clean_text(element.text) for element in root.iter() if _is_loc(element)]


def _is_loc(element: ElementTree.Element) -> bool:
    return _local_name(element.tag) == "loc" and bool(_clean_text(element.text))


def _local_name(tag: str) -> str:
    if "}" not in tag:
        return tag
    return tag.rsplit("}", 1)[1]


def _clean_text(value: str | None) -> str:
    if value is None:
        return ""
    return " ".join(value.split())
