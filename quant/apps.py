"""Django app configuration for Quant."""

from __future__ import annotations

from django.apps import AppConfig


class QuantConfig(AppConfig):
    """Register the Quant Django app.

    Example:
        `INSTALLED_APPS.append("quant.apps.QuantConfig")`
    """

    default_auto_field = "django.db.models.BigAutoField"
    name = "quant"
