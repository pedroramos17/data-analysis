"""Seed an idempotent development admin user."""

from django.conf import settings
from django.core.management.base import BaseCommand, CommandParser

from monitoring.dev_admin_seed import (
    resolve_dev_admin_credentials,
    upsert_dev_admin_user,
    validate_dev_admin_environment,
)


class Command(BaseCommand):
    """Create a development admin user with local-safe defaults.

    Example:
        `python3 manage.py seed_dev_admin --show-credentials`
    """

    help = "Seed a development admin user from DEV_ADMIN_* values or generated DEBUG credentials."

    def add_arguments(self, parser: CommandParser) -> None:
        """Register seed command options.

        Example:
            Django calls this before command execution.
        """

        parser.add_argument("--username", default="")
        parser.add_argument("--email", default="")
        parser.add_argument("--password", default="")
        parser.add_argument("--reset-password", action="store_true")
        parser.add_argument("--allow-production", action="store_true")
        parser.add_argument("--show-credentials", action="store_true")

    def handle(self, *args: object, **options: object) -> None:
        """Create or update the development admin user.

        Example:
            Django calls this after parsing command options.
        """

        credentials = resolve_dev_admin_credentials(
            str(options["username"]),
            str(options["email"]),
            str(options["password"]),
        )
        validate_dev_admin_environment(credentials, bool(options["allow_production"]))
        user, created = upsert_dev_admin_user(
            credentials,
            bool(options["reset_password"]),
        )
        status = "created" if created else "updated"
        self.stdout.write(f"Development admin {status}: {user.get_username()}")
        self._write_credentials(
            credentials.username,
            credentials.password,
            options,
            password_was_set=created or bool(options["reset_password"]),
        )

    def _write_credentials(
        self,
        username: str,
        password: str,
        options: dict[str, object],
        password_was_set: bool,
    ) -> None:
        if not bool(options["show_credentials"]):
            return
        if not settings.DEBUG:
            self.stdout.write("Credentials hidden because DEBUG=False")
            return
        self.stdout.write(f"Username: {username}")
        if not password_was_set:
            self.stdout.write("Password unchanged; pass --reset-password to update it")
            return
        self.stdout.write(f"Password: {password}")
