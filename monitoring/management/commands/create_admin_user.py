"""Create an idempotent admin user from environment variables."""

import os

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError, CommandParser


class Command(BaseCommand):
    """Create or update a Django superuser for local administration.

    Example:
        `python manage.py create_admin_user`
    """

    help = "Create an admin user from MONITOR_ADMIN_* environment variables."

    def add_arguments(self, parser: CommandParser) -> None:
        """Add the explicit password reset flag.

        Example:
            Django calls this before command execution.
        """
        parser.add_argument("--reset-password", action="store_true")

    def handle(self, *args: object, **options: object) -> None:
        """Create the superuser if it does not already exist.

        Example:
            Django calls this after parsing command options.
        """
        admin = _admin_env()
        user = _upsert_admin_user(admin, bool(options["reset_password"]))
        self.stdout.write(f"Admin user ready: {user.get_username()}")


def _admin_env() -> dict[str, str]:
    required = {
        "username": os.environ.get("MONITOR_ADMIN_USERNAME", ""),
        "email": os.environ.get("MONITOR_ADMIN_EMAIL", ""),
        "password": os.environ.get("MONITOR_ADMIN_PASSWORD", ""),
    }
    missing = [key for key, value in required.items() if not value]
    if missing:
        raise CommandError(_missing_env_error(missing))
    return required


def _upsert_admin_user(admin: dict[str, str], reset_password: bool) -> object:
    user_model = get_user_model()
    user, created = user_model.objects.get_or_create(
        username=admin["username"],
        defaults={"email": admin["email"], "is_staff": True, "is_superuser": True},
    )
    _update_admin_user(user, admin, created, reset_password)
    return user


def _update_admin_user(
    user: object,
    admin: dict[str, str],
    created: bool,
    reset_password: bool,
) -> None:
    user.email = admin["email"]
    user.is_staff = True
    user.is_superuser = True
    if created or reset_password:
        user.set_password(admin["password"])
    user.save()


def _missing_env_error(missing: list[str]) -> str:
    names = ", ".join(f"MONITOR_ADMIN_{name.upper()}" for name in missing)
    return f"Missing admin environment values {names!r}; expected username, email, and password"
