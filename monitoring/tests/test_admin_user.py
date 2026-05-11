"""Tests for idempotent admin user creation."""

from io import StringIO
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase


class AdminUserCommandTests(TestCase):
    """Admin user command regression tests."""

    def test_missing_env_values_fail_with_clear_error(self) -> None:
        """Admin creation requires all configured credentials."""
        with patch.dict("os.environ", {}, clear=True):
            with self.assertRaisesMessage(CommandError, "expected username"):
                call_command("create_admin_user", stdout=StringIO())

    def test_admin_user_is_created_once(self) -> None:
        """Repeated command calls do not duplicate the admin user."""
        env = _admin_env("secret-one")

        with patch.dict("os.environ", env, clear=True):
            call_command("create_admin_user", stdout=StringIO())
            call_command("create_admin_user", stdout=StringIO())

        self.assertEqual(get_user_model().objects.filter(username="monitor").count(), 1)

    def test_reset_password_updates_existing_user(self) -> None:
        """Password changes only when the reset flag is explicit."""
        user_model = get_user_model()
        with patch.dict("os.environ", _admin_env("secret-one"), clear=True):
            call_command("create_admin_user", stdout=StringIO())
        with patch.dict("os.environ", _admin_env("secret-two"), clear=True):
            call_command("create_admin_user", "--reset-password", stdout=StringIO())

        user = user_model.objects.get(username="monitor")
        self.assertTrue(user.check_password("secret-two"))


def _admin_env(password: str) -> dict[str, str]:
    return {
        "MONITOR_ADMIN_USERNAME": "monitor",
        "MONITOR_ADMIN_EMAIL": "monitor@example.org",
        "MONITOR_ADMIN_PASSWORD": password,
    }
