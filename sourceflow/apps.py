"""Django app configuration for canonical Sourceflow models."""

from __future__ import annotations

from django.apps import AppConfig


class SourceflowConfig(AppConfig):
    """Register additive canonical knowledge models."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "sourceflow"
    verbose_name = "Sourceflow canonical knowledge"
