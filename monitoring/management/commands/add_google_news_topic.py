"""Add a dynamic Google News RSS topic source."""

from django.core.management.base import BaseCommand, CommandParser

from monitoring.google_news import create_google_news_source


class Command(BaseCommand):
    """Create a Tier 4 dynamic Google News RSS source.

    Example:
        `python manage.py add_google_news_topic --query "AI chips" --category technology`
    """

    help = "Add a dynamic Google News RSS topic source."

    def add_arguments(self, parser: CommandParser) -> None:
        """Add query, category, and tags arguments.

        Example:
            Django calls this before command execution.
        """
        parser.add_argument("--query", required=True)
        parser.add_argument("--category", required=True)
        parser.add_argument("--tags", default="")

    def handle(self, *args: object, **options: object) -> None:
        """Create or update the topic source.

        Example:
            Django calls this after parsing command options.
        """
        source = create_google_news_source(
            query=str(options["query"]),
            category=str(options["category"]),
            tags=_tags_from_option(str(options["tags"])),
        )
        self.stdout.write(f"Created Google News source {source.id}: {source.name}")


def _tags_from_option(value: str) -> tuple[str, ...]:
    tags = [tag.strip().lower() for tag in value.split(",") if tag.strip()]
    return tuple(dict.fromkeys(tags))
