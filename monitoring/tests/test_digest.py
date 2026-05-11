"""Tests for feed digest grouping and caching."""

from datetime import UTC, datetime

from django.test import TestCase
from django.urls import reverse

from monitoring.digests import list_feed_digest_payload
from monitoring.models import DigestCache, NormalizedDocument, RawEvent, Source


class FeedDigestTests(TestCase):
    """Feed digest API and cache regression tests."""

    def test_digest_caps_category_and_source_items(self) -> None:
        """Digest grouping enforces per-category and per-source item caps."""
        source = _source("Source A")
        for index in range(6):
            _document(source, index)

        category_items = list_feed_digest_payload()["categories"]["security"]

        self.assertEqual(len(category_items), 5)

    def test_digest_api_returns_json_payload(self) -> None:
        """The digest API returns grouped recent documents as JSON."""
        source = _source("Source A")
        _document(source, 1)

        response = self.client.get(reverse("monitoring:feed-digest-api"))

        self.assertEqual(response.status_code, 200)
        self.assertIn("security", response.json()["categories"])

    def test_digest_payload_uses_cache_until_expiry(self) -> None:
        """Digest payload is reused while the SQLite cache is fresh."""
        source = _source("Source A")
        _document(source, 1, title="Cached Title")
        first_payload = list_feed_digest_payload()
        _document(source, 2, title="Uncached Title")

        second_payload = list_feed_digest_payload()

        self.assertEqual(first_payload, second_payload)
        self.assertEqual(DigestCache.objects.count(), 1)


def _source(name: str) -> Source:
    return Source.objects.create(
        name=name,
        url=f"https://example.org/{name}.xml",
        source_type=Source.SourceType.RSS,
        fetch_method=Source.FetchMethod.HTTP,
        category=Source.Category.SECURITY,
        tags=["security"],
    )


def _document(
    source: Source, index: int, title: str | None = None
) -> NormalizedDocument:
    raw_event = RawEvent.objects.create(
        source=source,
        url=f"https://example.org/{index}",
        content_hash=f"raw-{index}-{source.id}",
        payload_text="{}",
    )
    return NormalizedDocument.objects.create(
        source=source,
        raw_event=raw_event,
        canonical_url=f"https://example.org/{index}",
        title=title or f"Document {index}",
        published_at=datetime(2026, 5, 9, index % 23, tzinfo=UTC),
        content="Digest snippet",
        entities=["OpenAI"],
        tags=["security"],
        dedupe_hash=f"doc-{index}-{source.id}",
    )
