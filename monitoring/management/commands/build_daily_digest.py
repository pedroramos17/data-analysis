"""Build the admin-visible daily digest."""

from datetime import date

from django.core.management.base import BaseCommand, CommandParser

from monitoring.digests import build_daily_digest


class Command(BaseCommand):
    """Create or update a plain-text daily digest.

    Example:
        `python manage.py build_daily_digest --date 2026-05-09`
    """

    help = "Create or update a daily digest from normalized documents."

    def add_arguments(self, parser: CommandParser) -> None:
        """Add the optional digest date argument.

        Example:
            Django calls this before command execution.
        """
        parser.add_argument("--date", default=date.today().isoformat())

    def handle(self, *args: object, **options: object) -> None:
        """Build the requested digest.

        Example:
            Django calls this after parsing command options.
        """
        digest_date = date.fromisoformat(str(options["date"]))
        digest = build_daily_digest(digest_date)
        self.stdout.write(f"Built daily digest {digest.id}: {digest.title}")
