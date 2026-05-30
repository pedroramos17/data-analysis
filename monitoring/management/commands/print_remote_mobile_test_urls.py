"""Print configured remote mobile test URLs."""

from __future__ import annotations

from django.conf import settings
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    """Show local and public URLs for phone testing over mobile data."""

    help = "Print remote mobile testing URLs and security warnings."

    def handle(self, *args: object, **options: object) -> None:
        """Print configured local and public remote mobile URLs."""
        public_url = getattr(settings, "DEV_PUBLIC_BASE_URL", "") or "(not set)"
        provider = getattr(settings, "DEV_TUNNEL_PROVIDER", "") or "(not set)"
        notes = getattr(settings, "DEV_TUNNEL_NOTES", "") or "(none)"
        self.stdout.write("Local Django URL: http://127.0.0.1:8000")
        self.stdout.write(f"Public mobile URL: {public_url}")
        self.stdout.write(f"ALLOWED_HOSTS: {list(settings.ALLOWED_HOSTS)}")
        origins = list(getattr(settings, "CSRF_TRUSTED_ORIGINS", []))
        self.stdout.write(f"CSRF trusted origins: {origins}")
        self.stdout.write(f"Tunnel provider: {provider}")
        self.stdout.write(f"Tunnel notes: {notes}")
        self.stdout.write(
            "Warning: mobile-data testing requires a public HTTPS URL, "
            "for example Cloudflare Tunnel, ngrok, or a preview deployment."
        )
        self.stdout.write(
            "Warning: Do not expose admin publicly without authentication."
        )
