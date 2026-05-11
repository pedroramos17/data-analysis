"""Enrich normalized documents with local NLP metadata."""

from django.core.management.base import BaseCommand, CommandParser

from monitoring.enrichment import enrich_document
from monitoring.models import NormalizedDocument
from monitoring.option_parsing import optional_int


class Command(BaseCommand):
    """Run deterministic enrichment for normalized documents."""

    help = "Enrich normalized documents with local deterministic NLP metadata."

    def add_arguments(self, parser: CommandParser) -> None:
        """Add document limit and force options."""
        parser.add_argument("--limit", type=int, default=500)
        parser.add_argument("--force", action="store_true")

    def handle(self, *args: object, **options: object) -> None:
        """Execute document enrichment."""
        count = 0
        limit = optional_int(options.get("limit")) or 500
        for document in NormalizedDocument.objects.all()[:limit]:
            count += int(enrich_document(document, force=bool(options["force"])))
        self.stdout.write(f"Enriched {count} documents")
