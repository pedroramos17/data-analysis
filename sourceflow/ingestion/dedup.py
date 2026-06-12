"""Document hashing and duplicate-detection helpers."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import date, datetime
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

TRACKING_QUERY_PREFIXES = ("utm_",)
TRACKING_QUERY_KEYS = {"fbclid", "gclid", "mc_cid", "mc_eid"}


@dataclass(frozen=True)
class DuplicateCheck:
    """Result of checking one document against a known duplicate set."""

    is_duplicate: bool
    content_hash: str
    matched_document_id: int | None = None
    reason: str = ""


def canonicalize_url(raw_url: str) -> str:
    """Return a stable URL without fragments or common tracking parameters."""
    value = raw_url.strip()
    if not value:
        return ""
    parts = urlsplit(value)
    if not parts.scheme or not parts.netloc:
        raise ValueError(f"Invalid URL {raw_url!r}; expected absolute URL")
    query = urlencode(
        sorted(
            (key, query_value)
            for key, query_value in parse_qsl(parts.query, keep_blank_values=True)
            if _keep_query_key(key)
        ),
        doseq=True,
    )
    path = parts.path or "/"
    if path != "/" and path.endswith("/"):
        path = path[:-1]
    return urlunsplit((parts.scheme.lower(), _canonical_netloc(parts), path, query, ""))


def normalize_text(value: str) -> str:
    """Collapse whitespace while preserving word order."""
    return " ".join(value.split())


def content_hash(value: str) -> str:
    """Return a SHA-256 hash for normalized text content."""
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def document_content_hash(raw_text: str, clean_text: str = "") -> str:
    """Hash the clean text when present, falling back to raw text."""
    basis = clean_text if clean_text.strip() else raw_text
    return content_hash(normalize_text(basis))


def document_dedupe_key(
    *,
    source_id: str | int,
    url: str = "",
    external_id: str = "",
    title: str = "",
    published_at: datetime | date | str | None = None,
    clean_text: str = "",
) -> str:
    """Build a stable dedupe key for document-like inputs."""
    canonical_url = canonicalize_url(url) if url else ""
    if canonical_url:
        basis = f"url::{canonical_url}"
    elif external_id:
        basis = f"source::{source_id}::external::{external_id}"
    else:
        basis = "::".join(
            (
                "fallback",
                str(source_id),
                normalize_text(title).lower(),
                _date_part(published_at),
                normalize_text(clean_text)[:500].lower(),
            )
        )
    return content_hash(basis)


def detect_duplicate_hash(
    known_hashes: set[str] | list[str] | tuple[str, ...],
    candidate_hash: str,
) -> DuplicateCheck:
    """Check a candidate content hash against an in-memory hash collection."""
    duplicate = candidate_hash in set(known_hashes)
    return DuplicateCheck(
        is_duplicate=duplicate,
        content_hash=candidate_hash,
        reason="content_hash" if duplicate else "",
    )


def find_existing_document(*, source_id: int, content_hash_value: str, url: str = "") -> DuplicateCheck:
    """Check the canonical DB for an existing document.

    Django is imported lazily so pure utility imports work without project
    dependencies installed.
    """
    from sourceflow.models import Document

    queryset = Document.objects.filter(source_id=source_id, content_hash=content_hash_value)
    if url:
        queryset = queryset | Document.objects.filter(source_id=source_id, url=url)
    existing = queryset.order_by("id").first()
    return DuplicateCheck(
        is_duplicate=existing is not None,
        content_hash=content_hash_value,
        matched_document_id=existing.pk if existing else None,
        reason="content_hash_or_url" if existing else "",
    )


def _keep_query_key(key: str) -> bool:
    if key in TRACKING_QUERY_KEYS:
        return False
    return not any(key.startswith(prefix) for prefix in TRACKING_QUERY_PREFIXES)


def _canonical_netloc(parts: object) -> str:
    scheme = getattr(parts, "scheme").lower()
    netloc = getattr(parts, "netloc").lower()
    if scheme == "http" and netloc.endswith(":80"):
        return netloc[:-3]
    if scheme == "https" and netloc.endswith(":443"):
        return netloc[:-4]
    return netloc


def _date_part(value: datetime | date | str | None) -> str:
    if value is None:
        return ""
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    return str(value).strip()[:10]
