"""Ingest a local research PDF into ResearchSpace."""

from __future__ import annotations

from pathlib import Path

from django.core.files import File
from django.core.management.base import BaseCommand, CommandParser

from researchspace.services.pdf_extraction import ingest_uploaded_pdf


class Command(BaseCommand):
    """Store one local PDF as a ResearchSpace Paper."""

    help = "Ingest a local research PDF into ResearchSpace."

    def add_arguments(self, parser: CommandParser) -> None:
        """Register PDF ingestion options."""
        parser.add_argument("--path", required=True)
        parser.add_argument("--title", default="")

    def handle(self, *args: object, **options: object) -> None:
        """Ingest the PDF and print the resulting Paper id."""
        path = Path(str(options["path"]))
        if not path.exists():
            raise ValueError(f"Invalid PDF path {path}; expected existing file")
        with path.open("rb") as handle:
            result = ingest_uploaded_pdf(str(options["title"]), File(handle, path.name))
        self.stdout.write(f"paper_id={result.paper.pk} duplicate={result.duplicate}")
