"""Run the offline NLP pipeline from Django management."""

from __future__ import annotations

import json

from django.core.management.base import BaseCommand, CommandParser

from monitoring.nlp.metrics import save_nlp_run_metric
from monitoring.nlp.pipeline import run_pipeline


class Command(BaseCommand):
    """Run local CPU-first NLP tasks and persist run metrics."""

    help = "Run offline NLP tasks against explicit text."

    def add_arguments(self, parser: CommandParser) -> None:
        """Add text and task options.

        Example:
            Django calls this before parsing CLI arguments.
        """
        parser.add_argument("--text", required=True)
        parser.add_argument("--tasks", default="all")

    def handle(self, *args: object, **options: object) -> None:
        """Run the pipeline and print JSON.

        Example:
            `python manage.py nlp_pipeline --text "..." --tasks all`
        """
        result = run_pipeline(str(options["text"]), str(options["tasks"]))
        save_nlp_run_metric(result, "manage_command")
        self.stdout.write(json.dumps(result, indent=2, sort_keys=True))
