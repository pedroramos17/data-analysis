"""Normalize source payloads into canonical documents and chunks."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from sourceflow.ingestion.chunker import ChunkSpec, chunk_text
from sourceflow.ingestion.dedup import (
    DuplicateCheck,
    canonicalize_url,
    document_content_hash,
    document_dedupe_key,
    find_existing_document,
    normalize_text,
)

DEFAULT_INGESTION_VERSION = "sourceflow.phase2.v1"


@dataclass(frozen=True)
class DocumentInput:
    """Source-neutral document input for Phase 2 normalization."""

    source_id: int | str
    url: str = ""
    title: str = ""
    raw_text: str = ""
    clean_text: str = ""
    published_at: datetime | str | None = None
    ingested_at: datetime | str | None = None
    language: str = "en"
    external_id: str = ""
    metadata_json: dict[str, Any] = field(default_factory=dict)
    provenance_json: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class NormalizedDocument:
    """Canonical normalized document envelope before persistence."""

    source_id: int | str
    url: str
    title: str
    raw_text: str
    clean_text: str
    content_hash: str
    dedupe_key: str
    language: str
    published_at: datetime | None
    ingested_at: datetime | None
    metadata_json: dict[str, Any]
    provenance_json: dict[str, Any]
    ingestion_version: str
    chunks: list[ChunkSpec]


@dataclass(frozen=True)
class PersistedDocumentResult:
    """Result of writing a normalized document to canonical tables."""

    document: object
    chunks: list[object]
    duplicate: DuplicateCheck
    normalized: NormalizedDocument


def normalize_document_input(
    document_input: DocumentInput,
    *,
    ingestion_version: str = DEFAULT_INGESTION_VERSION,
    max_chunk_chars: int = 2_000,
    chunk_overlap: int = 200,
) -> NormalizedDocument:
    """Normalize a source-neutral document into the canonical envelope."""
    url = canonicalize_url(document_input.url) if document_input.url else ""
    raw_text = document_input.raw_text or document_input.clean_text or document_input.title
    clean_text = normalize_text(document_input.clean_text or document_input.raw_text)
    content_hash = document_content_hash(raw_text, clean_text)
    metadata_json = dict(document_input.metadata_json)
    metadata_json.setdefault("ingestion_version", ingestion_version)
    if document_input.external_id:
        metadata_json.setdefault("external_id", document_input.external_id)
    return NormalizedDocument(
        source_id=document_input.source_id,
        url=url,
        title=normalize_text(document_input.title),
        raw_text=raw_text,
        clean_text=clean_text,
        content_hash=content_hash,
        dedupe_key=document_dedupe_key(
            source_id=document_input.source_id,
            url=url,
            external_id=document_input.external_id,
            title=document_input.title,
            published_at=document_input.published_at,
            clean_text=clean_text,
        ),
        language=(document_input.language or "en").strip().lower() or "en",
        published_at=_coerce_datetime(document_input.published_at),
        ingested_at=_coerce_datetime(document_input.ingested_at),
        metadata_json=metadata_json,
        provenance_json=dict(document_input.provenance_json),
        ingestion_version=ingestion_version,
        chunks=chunk_text(clean_text, max_chars=max_chunk_chars, overlap=chunk_overlap),
    )


def persist_normalized_document(
    document_input: DocumentInput,
    *,
    ingestion_version: str = DEFAULT_INGESTION_VERSION,
    max_chunk_chars: int = 2_000,
    chunk_overlap: int = 200,
    update_existing: bool = False,
) -> PersistedDocumentResult:
    """Persist a normalized document and its chunks into canonical tables."""
    from django.utils import timezone
    from sourceflow.models import Document, DocumentChunk

    normalized = normalize_document_input(
        document_input,
        ingestion_version=ingestion_version,
        max_chunk_chars=max_chunk_chars,
        chunk_overlap=chunk_overlap,
    )
    duplicate = find_existing_document(
        source_id=int(normalized.source_id),
        content_hash_value=normalized.content_hash,
        url=normalized.url,
    )
    if duplicate.is_duplicate and not update_existing:
        document = Document.objects.get(pk=duplicate.matched_document_id)
        return PersistedDocumentResult(
            document=document,
            chunks=list(document.chunks.order_by("chunk_index")),
            duplicate=duplicate,
            normalized=normalized,
        )

    document_values = {
        "source_id": int(normalized.source_id),
        "url": normalized.url,
        "title": normalized.title,
        "published_at": normalized.published_at,
        "ingested_at": normalized.ingested_at or timezone.now(),
        "raw_text": normalized.raw_text,
        "clean_text": normalized.clean_text,
        "content_hash": normalized.content_hash,
        "language": normalized.language,
        "metadata_json": normalized.metadata_json,
        "provenance_json": normalized.provenance_json,
    }
    if duplicate.is_duplicate and update_existing:
        document = Document.objects.get(pk=duplicate.matched_document_id)
        for field_name, value in document_values.items():
            setattr(document, field_name, value)
        document.save()
    else:
        document = Document.objects.create(**document_values)

    chunk_rows: list[object] = []
    for chunk in normalized.chunks:
        chunk_row, _created = DocumentChunk.objects.update_or_create(
            document=document,
            chunk_index=chunk.chunk_index,
            defaults={
                "text": chunk.text,
                "char_start": chunk.char_start,
                "char_end": chunk.char_end,
                "token_count": chunk.token_count,
                "content_hash": chunk.content_hash,
                "language": normalized.language,
                "ingestion_version": normalized.ingestion_version,
                "metadata_json": {"dedupe_key": normalized.dedupe_key},
                "provenance_json": normalized.provenance_json,
            },
        )
        chunk_rows.append(chunk_row)
    return PersistedDocumentResult(
        document=document,
        chunks=chunk_rows,
        duplicate=duplicate,
        normalized=normalized,
    )


def _coerce_datetime(value: datetime | str | None) -> datetime | None:
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        parsed = value
    else:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)
