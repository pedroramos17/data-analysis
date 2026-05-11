"""Tests for idempotent storage and dedupe behavior."""

from datetime import UTC, datetime

from django.test import TestCase

from monitoring.contracts import FetchedRecord, FetchResult, ParsedRecord
from monitoring.models import NormalizedDocument, RawEvent, Source
from monitoring.storage import persist_fetched_record


class StorageDedupeTests(TestCase):
    """Database regression tests for raw-first idempotent writes."""

    def test_persist_fetched_record_is_idempotent(self) -> None:
        """Persisting the same fetched record twice creates one document."""
        source = _source()
        fetched_record = _fetched_record("https://example.org/a", "Stable Title")

        first_raw_created, first_doc_created = persist_fetched_record(
            source, fetched_record
        )
        second_raw_created, second_doc_created = persist_fetched_record(
            source, fetched_record
        )

        self.assertTrue(first_raw_created)
        self.assertTrue(first_doc_created)
        self.assertFalse(second_raw_created)
        self.assertFalse(second_doc_created)
        self.assertEqual(RawEvent.objects.count(), 1)
        self.assertEqual(NormalizedDocument.objects.count(), 1)

    def test_tracking_url_duplicate_keeps_one_document(self) -> None:
        """Different raw URLs that canonicalize together keep one document."""
        source = _source()
        clean = _fetched_record("https://example.org/a", "Stable Title")
        tracked = _fetched_record("https://example.org/a?utm_source=x", "Stable Title")

        persist_fetched_record(source, clean)
        raw_created, doc_created = persist_fetched_record(source, tracked)

        self.assertTrue(raw_created)
        self.assertFalse(doc_created)
        self.assertEqual(RawEvent.objects.count(), 2)
        self.assertEqual(NormalizedDocument.objects.count(), 1)


def _source() -> Source:
    return Source.objects.create(
        name="Example Source",
        url="https://example.org/feed.xml",
        source_type=Source.SourceType.RSS,
        fetch_method=Source.FetchMethod.HTTP,
        tags=["security"],
    )


def _fetched_record(url: str, title: str) -> FetchedRecord:
    parsed = ParsedRecord(url=url, title=title, content="Shared body")
    result = FetchResult(
        url=url,
        status_code=200,
        body="body",
        content_type="text/html",
        headers={},
        fetched_at=datetime(2026, 5, 8, tzinfo=UTC),
    )
    return FetchedRecord(result, parsed)
