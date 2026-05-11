"""Tests for arXiv source setup helpers."""

from io import StringIO
from urllib.parse import parse_qs, urlsplit

from django.core.management import call_command
from django.test import TestCase

from monitoring.models import Source


class ArxivSourceTests(TestCase):
    """Regression tests for official arXiv API source creation."""

    def test_add_arxiv_query_creates_bounded_disabled_api_source(self) -> None:
        """The command creates a reviewable source using arXiv API guidance."""
        output = StringIO()

        call_command(
            "add_arxiv_query",
            query="startup AI venture",
            max_results=10,
            stdout=output,
        )

        source = Source.objects.get(name="arXiv: startup AI venture")
        query = parse_qs(urlsplit(source.url).query)
        self.assertFalse(source.is_enabled)
        self.assertEqual(source.source_type, Source.SourceType.API)
        self.assertEqual(source.source_kind, Source.SourceKind.PAPER)
        self.assertEqual(source.rate_limit_seconds, 3)
        self.assertEqual(query["sortBy"], ["submittedDate"])
        self.assertEqual(query["sortOrder"], ["descending"])
        self.assertEqual(query["max_results"], ["10"])
        self.assertIn("Created arXiv source", output.getvalue())
