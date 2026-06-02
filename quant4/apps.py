"""Django app configuration for Quant4."""

from __future__ import annotations

from django.apps import AppConfig


class Quant4Config(AppConfig):
    """Register the Quant4 Django app.

    Example:
        `INSTALLED_APPS.append("quant4.apps.Quant4Config")`
    """

    default_auto_field = "django.db.models.BigAutoField"
    name = "quant4"
