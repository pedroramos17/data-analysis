"""Template context processors for monitoring."""

from __future__ import annotations

from django.conf import settings


def remote_mobile_testing(request: object) -> dict[str, object]:
    """Expose DEBUG-only remote mobile testing banner state.

    Example:
        Add this function to Django template context processors.
    """
    enabled = bool(getattr(settings, "REMOTE_MOBILE_TESTING_ENABLED", False))
    public_url = str(getattr(settings, "DEV_PUBLIC_BASE_URL", ""))
    provider = str(getattr(settings, "DEV_TUNNEL_PROVIDER", ""))
    return {
        "remote_mobile_testing_enabled": enabled and bool(settings.DEBUG),
        "remote_mobile_public_url": public_url,
        "remote_mobile_tunnel_provider": provider,
        "remote_mobile_admin_warning": (
            "Do not expose admin publicly without authentication."
        ),
    }
