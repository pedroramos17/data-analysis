"""Generate ResearchSpace factor candidates."""

from __future__ import annotations

from django.core.management.base import BaseCommand, CommandParser

from researchspace.models import QuantExtraction
from researchspace.services.factor_prompting import generate_factor_candidates


class Command(BaseCommand):
    """Generate factors from a QuantExtraction."""

    help = "Generate factor candidates from a ResearchSpace extraction."

    def add_arguments(self, parser: CommandParser) -> None:
        """Register generation options."""
        parser.add_argument("--extraction-id", required=True, type=int)

    def handle(self, *args: object, **options: object) -> None:
        """Print generated candidate count."""
        extraction = QuantExtraction.objects.get(pk=options["extraction_id"])
        candidates = generate_factor_candidates(extraction)
        self.stdout.write(f"generated={len(candidates)}")
