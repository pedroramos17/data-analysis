"""Set Sourceflow feature flag SQLite overrides."""

from __future__ import annotations

from django.core.management.base import BaseCommand, CommandParser

from sourceflow.config.feature_flags import parse_flag_value, set_feature_flag


class Command(BaseCommand):
    """Persist a Sourceflow feature flag override."""

    help = "Set a Sourceflow feature flag override in SQLite."

    def add_arguments(self, parser: CommandParser) -> None:
        """Register flag name and boolean value arguments."""
        parser.add_argument("name")
        parser.add_argument("value")

    def handle(self, *args: object, **options: object) -> None:
        """Persist and echo the resolved SQLite override."""
        enabled = parse_flag_value(options["value"])
        state = set_feature_flag(str(options["name"]), enabled)
        value = str(state.enabled).lower()
        self.stdout.write(f"{state.name}={value} source={state.source}")
