"""Tests for ingestion health and source cooldown behavior."""

from datetime import timedelta

from django.test import TestCase
from django.utils import timezone
from unittest.mock import patch

from monitoring.contracts import FetchedRecord, FetchResult, ParsedRecord
from monitoring.ingestion import IngestionService, RetryPolicy
from monitoring.models import IngestionCheckpoint, NormalizedDocument, Source


class FailingSourceAdapter:
    """Named fake adapter that always fails."""

    def fetch_records(self, limit: int | None = None) -> list[FetchedRecord]:
        """Raise a deterministic source failure.

        Example:
            `FailingSourceAdapter().fetch_records()`
        """
        raise RuntimeError("upstream feed unavailable")


class SuccessfulSourceAdapter:
    """Named fake adapter that returns one parsed public record."""

    def fetch_records(self, limit: int | None = None) -> list[FetchedRecord]:
        """Return one fetched record.

        Example:
            `SuccessfulSourceAdapter().fetch_records()`
        """
        return [_fetched_record()]


class IngestionHealthTests(TestCase):
    """Circuit breaker regression tests."""

    def test_source_enters_cooldown_after_two_failures(self) -> None:
        """Two source failures open the 5-minute circuit breaker."""
        source = _source()
        service = IngestionService(RetryPolicy(max_attempts=1, base_delay_seconds=0))

        with patch(
            "monitoring.ingestion.build_source_adapter",
            return_value=FailingSourceAdapter(),
        ):
            self._ignore_failure(service, source)
            self._ignore_failure(service, source)

        checkpoint = IngestionCheckpoint.objects.get(source=source)
        self.assertEqual(checkpoint.consecutive_failures, 2)
        self.assertGreater(checkpoint.cooldown_until, timezone.now())

    def test_source_recovers_after_cooldown_expires(self) -> None:
        """Expired cooldown allows a successful run to reset health state."""
        source = _source()
        checkpoint = IngestionCheckpoint.objects.create(
            source=source,
            consecutive_failures=2,
            cooldown_until=timezone.now() - timedelta(minutes=1),
        )
        service = IngestionService(RetryPolicy(max_attempts=1, base_delay_seconds=0))

        with patch(
            "monitoring.ingestion.build_source_adapter",
            return_value=SuccessfulSourceAdapter(),
        ):
            summary = service.ingest_source(source)

        checkpoint.refresh_from_db()
        self.assertEqual(summary.document_created_count, 1)
        self.assertEqual(checkpoint.consecutive_failures, 0)
        self.assertEqual(NormalizedDocument.objects.count(), 1)

    def _ignore_failure(self, service: IngestionService, source: Source) -> None:
        try:
            service.ingest_source(source)
        except RuntimeError:
            return


def _source() -> Source:
    return Source.objects.create(
        name="Failing Source",
        url="https://example.org/feed.xml",
        source_type=Source.SourceType.RSS,
        fetch_method=Source.FetchMethod.HTTP,
        category=Source.Category.SECURITY,
    )


def _fetched_record() -> FetchedRecord:
    result = FetchResult(
        url="https://example.org/1",
        status_code=200,
        body="body",
        content_type="text/xml",
        headers={},
        fetched_at=timezone.now(),
    )
    parsed = ParsedRecord(
        url="https://example.org/1",
        title="OpenAI Research",
        content="OpenAI Research released enough content for a digest item.",
    )
    return FetchedRecord(result, parsed)
