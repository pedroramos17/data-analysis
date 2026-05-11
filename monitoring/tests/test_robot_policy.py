"""Tests for RSS robots policy and due-source queue resilience."""

from io import StringIO
from unittest.mock import patch

from django.core.management import call_command
from django.test import TestCase

from monitoring.adapters import _request_for
from monitoring.models import Source


class RobotsPolicyTests(TestCase):
    """Robots policy regression tests for RSS feed fetching."""

    def test_rss_request_does_not_require_robots_validation(self) -> None:
        """RSS feeds bypass robots checks because they are explicit feed endpoints."""
        source = _source("RSS", Source.SourceType.RSS)

        request = _request_for(source)

        self.assertFalse(request.respect_robots)

    def test_non_rss_request_keeps_robots_validation(self) -> None:
        """HTML and crawler-style requests still use robots checks."""
        source = _source("HTML", Source.SourceType.HTML)

        request = _request_for(source)

        self.assertTrue(request.respect_robots)


class DueSourceQueueTests(TestCase):
    """Due-source command should not stop after one source failure."""

    def test_due_source_command_continues_after_source_failure(self) -> None:
        """One failing source is reported while later sources still run."""
        failing_source = _source("Failing", Source.SourceType.RSS)
        working_source = _source("Working", Source.SourceType.RSS)
        calls: list[int] = []

        def fake_ingest(service, source, limit=None):
            calls.append(source.id)
            if source.id == failing_source.id:
                raise RuntimeError("robots denied")
            return _summary(source.id or 0)

        with patch("monitoring.ingestion.IngestionService.ingest_source", fake_ingest):
            stderr = StringIO()
            stdout = StringIO()
            call_command("ingest_due_sources", stdout=stdout, stderr=stderr)

        self.assertEqual(calls, [failing_source.id, working_source.id])
        self.assertIn("Failed source", stderr.getvalue())
        self.assertIn("Ingested source", stdout.getvalue())


def _source(name: str, source_type: str) -> Source:
    return Source.objects.create(
        name=name,
        url=f"https://example.org/{name}.xml",
        source_type=source_type,
        fetch_method=Source.FetchMethod.HTTP,
        category=Source.Category.SECURITY,
    )


def _summary(source_id: int) -> object:
    from monitoring.contracts import IngestionSummary

    return IngestionSummary(source_id, 0, 0, 0, 0, 0)
