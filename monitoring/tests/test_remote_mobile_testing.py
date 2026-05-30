"""Tests for development-only remote mobile testing support."""

from __future__ import annotations

from io import StringIO
from unittest.mock import patch

from django.core.exceptions import ImproperlyConfigured
from django.core.management import call_command
from django.test import SimpleTestCase, TestCase, override_settings


class RemoteMobileSettingsTests(SimpleTestCase):
    """Remote mobile settings must stay DEBUG-only."""

    def test_wildcard_allowed_hosts_rejected_outside_debug(self) -> None:
        """Production-style config cannot use wildcard hosts."""
        from public_monitor.remote_mobile import build_remote_mobile_settings

        with self.assertRaisesRegex(ImproperlyConfigured, "ALLOWED_HOSTS"):
            build_remote_mobile_settings(
                debug=False,
                base_allowed_hosts=["example.com", "*"],
                environ={},
            )

    def test_remote_mobile_settings_do_not_activate_without_debug(self) -> None:
        """Tunnel hosts are ignored when DEBUG is false."""
        from public_monitor.remote_mobile import build_remote_mobile_settings

        result = build_remote_mobile_settings(
            debug=False,
            base_allowed_hosts=["example.com"],
            environ={
                "ENABLE_REMOTE_MOBILE_TESTING": "True",
                "DEV_PUBLIC_BASE_URL": "https://demo.trycloudflare.com",
                "DEV_EXTRA_ALLOWED_HOSTS": "demo.trycloudflare.com",
                "DEV_CSRF_TRUSTED_ORIGINS": "https://demo.trycloudflare.com",
            },
        )

        self.assertFalse(result.enabled)
        self.assertEqual(result.allowed_hosts, ["example.com"])
        self.assertEqual(result.csrf_trusted_origins, [])

    def test_csrf_trusted_origins_are_not_added_in_production(self) -> None:
        """CSRF tunnel origins remain DEBUG-only."""
        from public_monitor.remote_mobile import build_remote_mobile_settings

        result = build_remote_mobile_settings(
            debug=False,
            base_allowed_hosts=["example.com"],
            environ={
                "ENABLE_REMOTE_MOBILE_TESTING": "True",
                "DEV_CSRF_TRUSTED_ORIGINS": "https://demo.ngrok-free.app",
            },
        )

        self.assertEqual(result.csrf_trusted_origins, [])

    def test_debug_remote_mobile_settings_add_hosts_and_origins(self) -> None:
        """DEBUG tunnel hosts and CSRF origins are parsed from env."""
        from public_monitor.remote_mobile import build_remote_mobile_settings

        result = build_remote_mobile_settings(
            debug=True,
            base_allowed_hosts=["localhost", "127.0.0.1"],
            environ={
                "ENABLE_REMOTE_MOBILE_TESTING": "True",
                "DEV_PUBLIC_BASE_URL": "https://demo.trycloudflare.com",
                "DEV_EXTRA_ALLOWED_HOSTS": "demo.trycloudflare.com",
                "DEV_CSRF_TRUSTED_ORIGINS": "https://demo.trycloudflare.com",
                "DEV_TUNNEL_PROVIDER": "cloudflare",
            },
        )

        self.assertTrue(result.enabled)
        self.assertIn("demo.trycloudflare.com", result.allowed_hosts)
        self.assertEqual(
            result.csrf_trusted_origins,
            ["https://demo.trycloudflare.com"],
        )
        self.assertEqual(result.provider, "cloudflare")


class RemoteMobileCommandTests(SimpleTestCase):
    """Commands should explain remote mobile testing setup."""

    @override_settings(
        DEBUG=True,
        REMOTE_MOBILE_TESTING_ENABLED=True,
        DEV_PUBLIC_BASE_URL="https://demo.trycloudflare.com",
        DEV_TUNNEL_PROVIDER="cloudflare",
        DEV_TUNNEL_NOTES="temporary tunnel",
        ALLOWED_HOSTS=["localhost", "127.0.0.1", "demo.trycloudflare.com"],
        CSRF_TRUSTED_ORIGINS=["https://demo.trycloudflare.com"],
    )
    def test_print_remote_mobile_test_urls_outputs_public_https_url(self) -> None:
        """The URL helper prints local and public mobile testing details."""
        output = StringIO()

        call_command("print_remote_mobile_test_urls", stdout=output)

        text = output.getvalue()
        self.assertIn("http://127.0.0.1:8000", text)
        self.assertIn("https://demo.trycloudflare.com", text)
        self.assertIn("cloudflare", text)
        self.assertIn("public HTTPS URL", text)
        self.assertIn("Do not expose admin publicly", text)

    @override_settings(DEV_PUBLIC_BASE_URL="https://demo.ngrok-free.app")
    def test_print_mobile_qr_falls_back_to_plain_text(self) -> None:
        """QR output is optional when qrcode is not installed."""
        output = StringIO()

        call_command("print_mobile_qr", stdout=output)

        text = output.getvalue()
        self.assertIn("https://demo.ngrok-free.app", text)
        self.assertIn("qrcode package is optional", text)

    @override_settings(DEV_PUBLIC_BASE_URL="")
    def test_print_mobile_qr_reads_environment_url(self) -> None:
        """The QR helper can run before remote testing is enabled."""
        output = StringIO()

        with patch.dict(
            "os.environ",
            {"DEV_PUBLIC_BASE_URL": "https://demo.trycloudflare.com"},
        ):
            call_command("print_mobile_qr", stdout=output)

        text = output.getvalue()
        self.assertIn("https://demo.trycloudflare.com", text)


class RemoteMobileBannerTests(TestCase):
    """The DEBUG-only banner should warn before public admin exposure."""

    @override_settings(
        DEBUG=True,
        REMOTE_MOBILE_TESTING_ENABLED=True,
        DEV_PUBLIC_BASE_URL="https://demo.trycloudflare.com",
        DEV_TUNNEL_PROVIDER="cloudflare",
    )
    def test_admin_warning_banner_appears_in_debug_remote_testing_mode(self) -> None:
        """Remote testing pages show an explicit admin exposure warning."""
        response = self.client.get("/")

        self.assertContains(response, "Remote mobile testing is enabled")
        self.assertContains(response, "Do not expose admin publicly")
