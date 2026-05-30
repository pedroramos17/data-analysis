"""Tests for the development admin seed command."""

from io import StringIO
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase, override_settings


class SeedDevAdminCommandTests(TestCase):
    """Development admin seed command regression tests."""

    @override_settings(DEBUG=True)
    def test_default_debug_seed_creates_superuser(self) -> None:
        """Local DEBUG mode can use documented fallback credentials."""
        output = StringIO()

        with patch.dict("os.environ", {}, clear=True):
            call_command("seed_dev_admin", "--show-credentials", stdout=output)

        user = get_user_model().objects.get(username="admin")
        self.assertTrue(user.is_staff)
        self.assertTrue(user.is_superuser)
        self.assertTrue(user.is_active)
        self.assertTrue(user.check_password("admin12345"))
        self.assertIn("Password: admin12345", output.getvalue())

    @override_settings(DEBUG=True)
    def test_repeated_seed_does_not_duplicate_user(self) -> None:
        """The command is idempotent for the same username."""
        with patch.dict("os.environ", _dev_admin_env("secret-one"), clear=True):
            call_command("seed_dev_admin", stdout=StringIO())
            call_command("seed_dev_admin", stdout=StringIO())

        user_count = get_user_model().objects.filter(username="dev-admin").count()
        self.assertEqual(user_count, 1)

    @override_settings(DEBUG=True)
    def test_reset_password_updates_existing_user(self) -> None:
        """Existing passwords change only when reset is explicit."""
        with patch.dict("os.environ", _dev_admin_env("secret-one"), clear=True):
            call_command("seed_dev_admin", stdout=StringIO())
        with patch.dict("os.environ", _dev_admin_env("secret-two"), clear=True):
            call_command("seed_dev_admin", "--reset-password", stdout=StringIO())

        user = get_user_model().objects.get(username="dev-admin")
        self.assertTrue(user.check_password("secret-two"))

    @override_settings(DEBUG=False)
    def test_debug_false_blocks_without_allow_production(self) -> None:
        """Non-debug environments require an explicit production override."""
        with patch.dict("os.environ", _dev_admin_env("secret-one"), clear=True):
            with self.assertRaisesMessage(CommandError, "DEBUG=False"):
                call_command("seed_dev_admin", stdout=StringIO())

    @override_settings(DEBUG=False)
    def test_debug_false_blocks_fallback_password(self) -> None:
        """Production override still rejects the documented fallback password."""
        with patch.dict("os.environ", {}, clear=True):
            with self.assertRaisesMessage(CommandError, "fallback password"):
                call_command(
                    "seed_dev_admin",
                    "--allow-production",
                    stdout=StringIO(),
                )

    @override_settings(DEBUG=True)
    def test_cli_values_override_environment_values(self) -> None:
        """CLI credentials have precedence over DEV_ADMIN_* variables."""
        with patch.dict("os.environ", _dev_admin_env("env-secret"), clear=True):
            call_command(
                "seed_dev_admin",
                "--username",
                "cli-admin",
                "--email",
                "cli@example.local",
                "--password",
                "cli-secret",
                stdout=StringIO(),
            )

        user = get_user_model().objects.get(username="cli-admin")
        self.assertEqual(user.email, "cli@example.local")
        self.assertTrue(user.check_password("cli-secret"))


def _dev_admin_env(password: str) -> dict[str, str]:
    return {
        "DEV_ADMIN_USERNAME": "dev-admin",
        "DEV_ADMIN_EMAIL": "dev-admin@example.local",
        "DEV_ADMIN_PASSWORD": password,
    }
