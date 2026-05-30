"""Ingest enabled RSS sources for comparison workflows."""

from django.core.management.base import BaseCommand, CommandParser

from monitoring.ingestion import IngestionService
from monitoring.models import Source
from monitoring.option_parsing import optional_int


class Command(BaseCommand):
    """Fetch and normalize enabled RSS feeds."""

    help = "Fetch, parse, normalize, and store enabled RSS sources."

    def add_arguments(self, parser: CommandParser) -> None:
        """Add ingestion options.

        Example:
            Django calls this before command execution.
        """
        parser.add_argument("--limit", type=int, default=20)
        parser.add_argument("--source-id", action="append", default=[])

    def handle(self, *args: object, **options: object) -> None:
        """Run RSS ingestion.

        Example:
            `python manage.py ingest_rss --limit 50`
        """
        limit = optional_int(options.get("limit"))
        sources = _rss_sources(options["source_id"])
        created_count = _ingest_sources(sources, limit)
        self.stdout.write(f"Ingested RSS sources; created {created_count} articles")


def _rss_sources(source_ids: list[str]) -> list[Source]:
    sources = Source.objects.filter(is_enabled=True, source_type=Source.SourceType.RSS)
    if source_ids:
        sources = sources.filter(pk__in=[int(source_id) for source_id in source_ids])
    return list(sources)


def _ingest_sources(sources: list[Source], limit: int | None) -> int:
    service = IngestionService()
    created_count = 0
    for source in sources:
        summary = service.ingest_source(source, limit=limit)
        created_count += summary.document_created_count
    return created_count
