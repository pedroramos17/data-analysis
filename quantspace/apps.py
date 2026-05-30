"""QuantSpace Django app configuration."""

from __future__ import annotations

from django.apps import AppConfig


class QuantspaceConfig(AppConfig):
    """Register the local-first research cockpit app."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "quantspace"
    verbose_name = "QuantSpace"
