"""Build a local QuantSpace paper search index."""

from __future__ import annotations

from django.core.management.base import BaseCommand, CommandParser

from quantspace.models import Paper
from quantspace.services.vector_search import build_paper_index


class Command(BaseCommand):
    """Build the simple vector-search index marker."""

    help = "Build a local search index for one paper."

    def add_arguments(self, parser: CommandParser) -> None:
        """Register paper selection options."""
        parser.add_argument("--paper-id", required=True, type=int)

    def handle(self, *args: object, **options: object) -> None:
        """Print the index build result."""
        paper = Paper.objects.get(pk=options["paper_id"])
        self.stdout.write(build_paper_index(paper))
