"""Idempotent database writes for raw and normalized ingestion data."""

import json
from dataclasses import asdict

from django.db import transaction

from monitoring.contracts import FetchedRecord, NormalizedRecord, ParsedRecord
from monitoring.entities import index_document_entities
from monitoring.enrichment import enrich_document
from monitoring.models import DeadLetter, NormalizedDocument, RawEvent, Source
from monitoring.normalizers import build_content_hash, normalize_record
from monitoring.services.deduplication import content_hash, simhash_text, url_hash
from monitoring.snapshots import save_fetch_snapshot


@transaction.atomic
def persist_fetched_record(
    source: Source,
    fetched_record: FetchedRecord,
) -> tuple[bool, bool]:
    """Store raw data first, then normalized data.

    Example:
        `raw_created, doc_created = persist_fetched_record(source, fetched_record)`
    """
    raw_event, raw_created = store_raw_record(source, fetched_record)
    normalized = normalize_record(
        _source_name(source),
        _source_tags(source),
        fetched_record.parsed_record,
    )
    _document, doc_created = store_normalized_document(source, raw_event, normalized)
    if doc_created:
        index_document_entities(_document)
        enrich_document(_document)
    return raw_created, doc_created


def store_raw_record(
    source: Source,
    fetched_record: FetchedRecord,
) -> tuple[RawEvent, bool]:
    """Store a raw parsed record idempotently by source and content hash.

    Example:
        `raw_event, created = store_raw_record(source, fetched_record)`
    """
    payload = _record_payload(fetched_record.parsed_record)
    content_hash = build_content_hash(payload)
    defaults = _raw_event_defaults(source, fetched_record, payload)
    return RawEvent.objects.get_or_create(
        source=source,
        content_hash=content_hash,
        defaults=defaults,
    )


def store_normalized_document(
    source: Source,
    raw_event: RawEvent,
    record: NormalizedRecord,
) -> tuple[NormalizedDocument, bool]:
    """Store a normalized document idempotently by dedupe hash.

    Example:
        `document, created = store_normalized_document(source, raw_event, record)`
    """
    return NormalizedDocument.objects.get_or_create(
        dedupe_hash=record.dedupe_hash,
        defaults=_document_defaults(source, raw_event, record),
    )


def store_dead_letter(
    source: Source,
    url: str,
    reason: str,
    payload_excerpt: str = "",
    raw_event: RawEvent | None = None,
) -> DeadLetter:
    """Store a failed page or bad record for admin review.

    Example:
        `store_dead_letter(source, source.url, "Parse failed")`
    """
    return DeadLetter.objects.create(
        source=source,
        raw_event=raw_event,
        url=url,
        reason=reason,
        payload_excerpt=payload_excerpt[:2000],
    )


def _record_payload(record: ParsedRecord) -> str:
    return json.dumps(asdict(record), ensure_ascii=True, sort_keys=True)


def _raw_event_defaults(
    source: Source, fetched_record: FetchedRecord, payload: str
) -> dict[str, object]:
    result = fetched_record.fetch_result
    record = fetched_record.parsed_record
    return {
        "url": record.url or result.url,
        "external_id": record.external_id,
        "payload_text": payload,
        "http_status": result.status_code,
        "headers": dict(result.headers),
        "fetched_at": result.fetched_at,
        "snapshot_path": save_fetch_snapshot(source=source, fetch_result=result),
    }


def _document_defaults(
    source: Source,
    raw_event: RawEvent,
    record: NormalizedRecord,
) -> dict[str, object]:
    text = record.content
    hash_basis = f"{record.title}\n{text}"
    return {
        "source": source,
        "raw_event": raw_event,
        "url": raw_event.url,
        "canonical_url": record.canonical_url,
        "url_hash": url_hash(record.canonical_url),
        "title": record.title,
        "description": record.content[:700],
        "author": record.author,
        "published_at": record.published_at,
        "fetched_at": raw_event.fetched_at,
        "language": record.language,
        "content": record.content,
        "text": text,
        "extracted_text": text,
        "entities": list(record.entities),
        "tags": list(record.tags),
        "content_hash": content_hash(hash_basis),
        "simhash": simhash_text(hash_basis),
        "status": NormalizedDocument.Status.NORMALIZED,
        "metadata": dict(record.metadata),
    }


def _source_name(source: Source) -> str:
    return source.name or f"source:{source.pk}"


def _source_tags(source: Source) -> tuple[str, ...]:
    return tuple(str(tag) for tag in source.tags)
