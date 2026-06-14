"""Extract Quant methodology from a ResearchSpace paper."""

from __future__ import annotations

from django.core.management.base import BaseCommand, CommandParser

from researchspace.models import Paper
from researchspace.services.quant_extraction import extract_quant_methodology


class Command(BaseCommand):
    """Create a QuantExtraction for one paper."""

    help = "Extract Quant methodology from one ResearchSpace paper."

    def add_arguments(self, parser: CommandParser) -> None:
        """Register extraction options."""
        parser.add_argument("--paper-id", required=True, type=int)

    def handle(self, *args: object, **options: object) -> None:
        """Print the created extraction id."""
        paper = Paper.objects.get(pk=options["paper_id"])
        extraction = extract_quant_methodology(paper)
        self.stdout.write(f"extraction_id={extraction.pk}")
