"""Tests for URL, timestamp, tag, entity, and option normalization."""

from datetime import UTC

from django.test import SimpleTestCase

from monitoring.contracts import ParsedRecord
from monitoring.ingestion import RetryPolicy, calculate_backoff
from monitoring.normalizers import (
    canonicalize_url,
    merge_tags,
    normalize_record,
    parse_publication_datetime,
)
from monitoring.option_parsing import optional_int


class NormalizerTests(SimpleTestCase):
    """Core normalization regression tests."""

    def test_canonicalize_url_removes_tracking_values(self) -> None:
        """URL normalization removes tracking query params and fragments."""
        url = "HTTPS://Example.Org:443/post?b=2&utm_source=x&a=1#section"

        self.assertEqual(canonicalize_url(url), "https://example.org/post?a=1&b=2")

    def test_parse_publication_datetime_returns_utc(self) -> None:
        """Timestamp parsing accepts RFC 2822 and returns UTC datetimes."""
        parsed = parse_publication_datetime("Fri, 08 May 2026 12:30:00 GMT")

        self.assertIsNotNone(parsed)
        self.assertEqual(parsed.tzinfo, UTC)

    def test_normalize_record_builds_entities_tags_and_hash(self) -> None:
        """Record normalization merges tags and produces stable dedupe hashes."""
        parsed = ParsedRecord(
            url="https://example.org/post?utm_source=x",
            title="OpenAI Research Update",
            content="Django Foundation reviewed OpenAI Research workflows.",
        )

        first = normalize_record("Example", ("security",), parsed)
        second = normalize_record("Example", ("security",), parsed)

        self.assertEqual(first.tags, ("security",))
        self.assertIn("OpenAI Research Update", first.entities)
        self.assertEqual(first.dedupe_hash, second.dedupe_hash)

    def test_merge_tags_deduplicates_in_order(self) -> None:
        """Tag merging preserves first occurrence."""
        tags = merge_tags(("Security", "python"), ("security", "cve"))

        self.assertEqual(tags, ("security", "python", "cve"))

    def test_optional_int_accepts_none_and_strings(self) -> None:
        """Command option parsing keeps absent values absent."""
        self.assertIsNone(optional_int(None))
        self.assertEqual(optional_int("10"), 10)

    def test_calculate_backoff_is_exponential(self) -> None:
        """Retry backoff doubles on each retry attempt."""
        policy = RetryPolicy(max_attempts=3, base_delay_seconds=0.5)

        self.assertEqual(calculate_backoff(3, policy), 2.0)
