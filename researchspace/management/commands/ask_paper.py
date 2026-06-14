"""Ask a retrieval-first question over one ResearchSpace paper."""

from __future__ import annotations

from django.core.management.base import BaseCommand, CommandParser

from researchspace.models import Paper
from researchspace.services.ask_paper import answer_paper_question


class Command(BaseCommand):
    """Ask one local paper question."""

    help = "Ask a retrieval-first question over one ResearchSpace paper."

    def add_arguments(self, parser: CommandParser) -> None:
        """Register ask options."""
        parser.add_argument("--paper-id", required=True, type=int)
        parser.add_argument("--question", required=True)

    def handle(self, *args: object, **options: object) -> None:
        """Print answer and prompt preview."""
        paper = Paper.objects.get(pk=options["paper_id"])
        result = answer_paper_question(paper, str(options["question"]))
        self.stdout.write(str(result["answer"]))
        self.stdout.write(str(result["prompt_preview"]))
