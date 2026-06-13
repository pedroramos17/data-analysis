"""ResearchSpace Django app configuration."""

from __future__ import annotations

from django.apps import AppConfig


class ResearchspaceConfig(AppConfig):
    """Register the local-first research cockpit app."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "researchspace"
    verbose_name = "ResearchSpace"
