"""Ingest one source by ID."""

from django.core.management.base import BaseCommand, CommandParser

from monitoring.ingestion import IngestionService
from monitoring.models import Source
from monitoring.option_parsing import optional_int


class Command(BaseCommand):
    """Run ingestion for one registered source.

    Example:
        `python manage.py ingest_source --source-id 1 --limit 20`
    """

    help = "Fetch, parse, normalize, and store one source."

    def add_arguments(self, parser: CommandParser) -> None:
        """Add source and limit arguments.

        Example:
            Django calls this before command execution.
        """
        parser.add_argument("--source-id", required=True, type=int)
        parser.add_argument("--limit", type=int, default=None)

    def handle(self, *args: object, **options: object) -> None:
        """Execute ingestion for the requested source.

        Example:
            Django calls this after parsing command options.
        """
        source_id = int(options["source_id"])
        limit = optional_int(options.get("limit"))
        source = Source.objects.get(pk=source_id)
        summary = IngestionService().ingest_source(source, limit=limit)
        self.stdout.write(
            _summary_line(summary.source_id, summary.document_created_count)
        )


def _summary_line(source_id: int, created_count: int) -> str:
    return f"Ingested source {source_id}; created {created_count} normalized documents"
