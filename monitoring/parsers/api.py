"""Parser for approved public JSON API responses."""

import json
from collections.abc import Iterable, Mapping

from monitoring.contracts import ParsedRecord


def parse_api_records(
    json_text: str, source_tags: tuple[str, ...] = ()
) -> list[ParsedRecord]:
    """Parse a simple approved public JSON API response.

    Example:
        `records = parse_api_records('{"items": []}')`
    """
    payload = json.loads(json_text)
    items = _payload_items(payload)
    return [_record_from_mapping(item, source_tags) for item in items]


def _payload_items(payload: object) -> list[Mapping[str, object]]:
    if isinstance(payload, list):
        return _mapping_items(payload)
    if isinstance(payload, Mapping):
        return _mapping_items(payload.get("items", []))
    raise ValueError(f"Invalid API payload {type(payload)!r}; expected list or object")


def _mapping_items(value: object) -> list[Mapping[str, object]]:
    if not isinstance(value, Iterable) or isinstance(value, str | bytes):
        raise ValueError(f"Invalid API items {value!r}; expected list of objects")
    return [item for item in value if isinstance(item, Mapping)]


def _record_from_mapping(
    item: Mapping[str, object],
    tags: tuple[str, ...],
) -> ParsedRecord:
    url = _string_value(item, "url", "link")
    title = _string_value(item, "title", "name") or url
    content = _string_value(item, "content", "body", "summary", "description")
    published = _string_value(item, "published_at", "published", "updated_at")
    author = _string_value(item, "author", "byline")
    external_id = _string_value(item, "id", "guid") or url
    return ParsedRecord(url, title, content, external_id, author, published, tags=tags)


def _string_value(item: Mapping[str, object], *keys: str) -> str:
    for key in keys:
        value = item.get(key)
        if value:
            return str(value)
    return ""
