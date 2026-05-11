"""Normalization pipeline for parsed public-source records."""

import hashlib
import re
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from monitoring.contracts import NormalizedRecord, ParsedRecord

TRACKING_QUERY_PREFIXES = ("utm_",)
TRACKING_QUERY_KEYS = {"fbclid", "gclid", "mc_cid", "mc_eid"}
ENTITY_PATTERN = re.compile(
    r"\b[A-Z][A-Za-z0-9&.-]*(?:[ \t]+[A-Z][A-Za-z0-9&.-]*){0,4}\b"
)


def normalize_record(
    source_name: str,
    source_tags: tuple[str, ...],
    parsed_record: ParsedRecord,
) -> NormalizedRecord:
    """Normalize one parsed record into canonical document fields.

    Example:
        `normalized = normalize_record("CISA", ("security",), parsed_record)`
    """
    canonical_url = canonicalize_url(parsed_record.url)
    title = normalize_title(parsed_record.title, canonical_url)
    content = normalize_whitespace(parsed_record.content)
    tags = merge_tags(source_tags, parsed_record.tags)
    published_at = parse_publication_datetime(parsed_record.published_text)
    dedupe_hash = build_dedupe_hash(source_name, canonical_url, title, content)
    return NormalizedRecord(
        canonical_url,
        title,
        parsed_record.author.strip(),
        published_at,
        parsed_record.language.strip().lower(),
        content,
        extract_entities(title, content),
        tags,
        dedupe_hash,
        dict(parsed_record.metadata),
    )


def canonicalize_url(raw_url: str) -> str:
    """Canonicalize a public URL for dedupe and display.

    Example:
        `canonicalize_url("HTTPS://Example.com/a?utm_source=x#top")`
    """
    parts = urlsplit(raw_url.strip())
    if not parts.scheme or not parts.netloc:
        raise ValueError(f"Invalid URL {raw_url!r}; expected absolute URL")
    query = _canonical_query(parts.query)
    netloc = _canonical_netloc(parts.scheme.lower(), parts.netloc.lower())
    path = parts.path or "/"
    return urlunsplit((parts.scheme.lower(), netloc, path, query, ""))


def normalize_title(title: str, fallback_url: str) -> str:
    """Return a compact title or fall back to the URL.

    Example:
        `normalize_title("  My   Title ", "https://example.com/")`
    """
    normalized = normalize_whitespace(title)
    return normalized or fallback_url


def normalize_whitespace(value: str) -> str:
    """Collapse whitespace without changing words.

    Example:
        `normalize_whitespace("a\\n  b")`
    """
    return " ".join(value.split())


def parse_publication_datetime(value: str) -> datetime | None:
    """Parse common public-feed timestamps into UTC.

    Example:
        `parse_publication_datetime("2026-05-08T10:00:00Z")`
    """
    if not value.strip():
        return None
    parsed = _parse_iso_datetime(value) or _parse_email_datetime(value)
    if parsed is None:
        raise ValueError(f"Invalid timestamp {value!r}; expected ISO 8601 or RFC 2822")
    return _to_utc(parsed)


def merge_tags(
    source_tags: tuple[str, ...], record_tags: tuple[str, ...]
) -> tuple[str, ...]:
    """Merge source and record tags while preserving first occurrence.

    Example:
        `merge_tags(("security",), ("cve", "security"))`
    """
    clean_tags = [
        tag.strip().lower() for tag in source_tags + record_tags if tag.strip()
    ]
    return tuple(dict.fromkeys(clean_tags))


def extract_entities(title: str, content: str) -> tuple[str, ...]:
    """Extract simple title-cased entity candidates.

    Example:
        `extract_entities("OpenAI Research", "OpenAI released a paper.")`
    """
    text = f"{title}\n{content}"
    matches = ENTITY_PATTERN.findall(text)
    return tuple(
        dict.fromkeys(match.strip() for match in matches if _entity_is_useful(match))
    )


def build_dedupe_hash(source_name: str, url: str, title: str, content: str) -> str:
    """Build a stable document hash.

    Example:
        `build_dedupe_hash("CISA", url, "Title", "Body")`
    """
    basis = "\n".join((source_name.strip().lower(), url, title.lower(), content[:500]))
    return hashlib.sha256(basis.encode("utf-8")).hexdigest()


def build_content_hash(value: str) -> str:
    """Build a stable SHA-256 hash for raw payload text.

    Example:
        `build_content_hash("<xml />")`
    """
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _canonical_query(query: str) -> str:
    pairs = parse_qsl(query, keep_blank_values=True)
    clean_pairs = [(key, value) for key, value in pairs if _keep_query_key(key)]
    return urlencode(sorted(clean_pairs), doseq=True)


def _keep_query_key(key: str) -> bool:
    if key in TRACKING_QUERY_KEYS:
        return False
    return not any(key.startswith(prefix) for prefix in TRACKING_QUERY_PREFIXES)


def _canonical_netloc(scheme: str, netloc: str) -> str:
    if scheme == "http" and netloc.endswith(":80"):
        return netloc[:-3]
    if scheme == "https" and netloc.endswith(":443"):
        return netloc[:-4]
    return netloc


def _parse_iso_datetime(value: str) -> datetime | None:
    try:
        return datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except ValueError:
        return None


def _parse_email_datetime(value: str) -> datetime | None:
    try:
        return parsedate_to_datetime(value)
    except (TypeError, ValueError, IndexError):
        return None


def _to_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _entity_is_useful(value: str) -> bool:
    return len(value) > 2 and value.lower() not in {"the", "and", "for"}
