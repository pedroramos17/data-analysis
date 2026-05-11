"""Ingest all due enabled sources."""

from django.core.management.base import BaseCommand, CommandParser
from django.utils import timezone

from monitoring.ingestion import IngestionService
from monitoring.option_parsing import optional_int
from monitoring.scheduling import find_due_sources


class Command(BaseCommand):
    """Run ingestion for sources whose cadence has elapsed.

    Example:
        `python manage.py ingest_due_sources --limit 20`
    """

    help = "Fetch, parse, normalize, and store due sources."

    def add_arguments(self, parser: CommandParser) -> None:
        """Add the optional source count limit.

        Example:
            Django calls this before command execution.
        """
        parser.add_argument("--limit", type=int, default=None)

    def handle(self, *args: object, **options: object) -> None:
        """Execute ingestion for all due sources.

        Example:
            Django calls this after parsing command options.
        """
        service = IngestionService()
        sources = find_due_sources(timezone.now(), optional_int(options.get("limit")))
        for source in sources:
            try:
                summary = service.ingest_source(source)
            except Exception as error:
                self.stderr.write(_failure_line(source.id or 0, error))
                continue
            self.stdout.write(_source_line(summary.source_id, summary.parsed_count))


def _source_line(source_id: int, parsed_count: int) -> str:
    return f"Ingested source {source_id}; parsed {parsed_count} records"


def _failure_line(source_id: int, error: Exception) -> str:
    return f"Failed source {source_id}; {type(error).__name__}: {error}"
