"""Export QuantSpace chunks to Parquet."""

from __future__ import annotations

from django.core.management.base import BaseCommand, CommandParser

from quantspace.models import Paper
from quantspace.services.chunk_export import export_paper_chunks_to_parquet


class Command(BaseCommand):
    """Export one paper's chunks to Parquet."""

    help = "Export QuantSpace paper chunks to Parquet."

    def add_arguments(self, parser: CommandParser) -> None:
        """Register export options."""
        parser.add_argument("--paper-id", required=True, type=int)

    def handle(self, *args: object, **options: object) -> None:
        """Print the created artifact path."""
        paper = Paper.objects.get(pk=options["paper_id"])
        artifact = export_paper_chunks_to_parquet(paper)
        self.stdout.write(f"artifact_id={artifact.pk} path={artifact.path}")
