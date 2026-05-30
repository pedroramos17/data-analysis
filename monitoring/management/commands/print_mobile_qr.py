"""Print the public mobile URL and optional QR output."""

from __future__ import annotations

import os

from django.conf import settings
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    """Print DEV_PUBLIC_BASE_URL for phone scanning."""

    help = "Print a QR-friendly remote mobile testing URL."

    def handle(self, *args: object, **options: object) -> None:
        """Print a plain URL and optional ASCII QR code."""
        public_url = (
            os.getenv("DEV_PUBLIC_BASE_URL")
            or str(getattr(settings, "DEV_PUBLIC_BASE_URL", ""))
        ).strip()
        if not public_url:
            self.stdout.write("DEV_PUBLIC_BASE_URL is not set.")
            return
        self.stdout.write(public_url)
        self.stdout.write("The qrcode package is optional for terminal QR output.")
        self._print_optional_qr(public_url)

    def _print_optional_qr(self, public_url: str) -> None:
        try:
            import qrcode
        except ImportError:
            self.stdout.write("Install qrcode only if you want ASCII QR output.")
            return
        qr = qrcode.QRCode(border=1)
        qr.add_data(public_url)
        qr.make(fit=True)
        qr.print_ascii(out=self.stdout)
