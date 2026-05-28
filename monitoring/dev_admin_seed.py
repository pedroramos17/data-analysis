"""Development admin seed helpers."""

import os
from dataclasses import dataclass

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.management.base import CommandError


DEV_ADMIN_DEFAULT_USERNAME = "admin"
DEV_ADMIN_DEFAULT_EMAIL = "admin@example.local"
DEV_ADMIN_DEFAULT_PASSWORD = "admin12345"


@dataclass(frozen=True)
class DevAdminCredentials:
    """Resolved development admin credentials.

    Example:
        `credentials = resolve_dev_admin_credentials("", "", "")`
    """

    username: str
    email: str
    password: str
    password_source: str


def resolve_dev_admin_credentials(
    username_override: str,
    email_override: str,
    password_override: str,
) -> DevAdminCredentials:
    """Resolve CLI values before environment values and local defaults.

    Example:
        `credentials = resolve_dev_admin_credentials("admin", "", "")`
    """

    username = _first_value(
        username_override,
        os.environ.get("DEV_ADMIN_USERNAME", ""),
        DEV_ADMIN_DEFAULT_USERNAME,
    )
    email = _first_value(
        email_override,
        os.environ.get("DEV_ADMIN_EMAIL", ""),
        DEV_ADMIN_DEFAULT_EMAIL,
    )
    password, password_source = _password_with_source(password_override)
    return DevAdminCredentials(username, email, password, password_source)


def validate_dev_admin_environment(
    credentials: DevAdminCredentials,
    allow_production: bool,
) -> None:
    """Block fallback credentials outside DEBUG unless explicitly allowed.

    Example:
        `validate_dev_admin_environment(credentials, allow_production=False)`
    """

    if settings.DEBUG:
        return
    if not allow_production:
        raise CommandError(
            "Refusing seed_dev_admin with DEBUG=False; expected --allow-production"
        )
    if credentials.password_source == "fallback":
        raise CommandError(
            "Refusing fallback password 'admin12345' with DEBUG=False; "
            "expected DEV_ADMIN_PASSWORD or --password"
        )


def upsert_dev_admin_user(
    credentials: DevAdminCredentials,
    reset_password: bool,
) -> tuple[object, bool]:
    """Create or update the development superuser idempotently.

    Example:
        `user, created = upsert_dev_admin_user(credentials, reset_password=False)`
    """

    user_model = get_user_model()
    user, created = user_model.objects.get_or_create(
        username=credentials.username,
        defaults={
            "email": credentials.email,
            "is_active": True,
            "is_staff": True,
            "is_superuser": True,
        },
    )
    _update_dev_admin_user(user, credentials, created, reset_password)
    return user, bool(created)


def _password_with_source(password_override: str) -> tuple[str, str]:
    if password_override:
        return password_override, "cli"
    env_password = os.environ.get("DEV_ADMIN_PASSWORD", "")
    if env_password:
        return env_password, "env"
    return DEV_ADMIN_DEFAULT_PASSWORD, "fallback"


def _first_value(override: str, env_value: str, default_value: str) -> str:
    if override:
        return override
    if env_value:
        return env_value
    return default_value


def _update_dev_admin_user(
    user: object,
    credentials: DevAdminCredentials,
    created: bool,
    reset_password: bool,
) -> None:
    user.email = credentials.email
    user.is_active = True
    user.is_staff = True
    user.is_superuser = True
    if created or reset_password:
        user.set_password(credentials.password)
    user.save()
