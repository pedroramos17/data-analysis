"""List Sourceflow feature flags."""

from __future__ import annotations

from django.core.management.base import BaseCommand

from sourceflow.config.feature_flags import list_feature_flags


class Command(BaseCommand):
    """Print resolved Sourceflow feature flag states."""

    help = "List Sourceflow feature flags and resolution sources."

    def handle(self, *args: object, **options: object) -> None:
        """Print one flag per line."""
        for state in list_feature_flags():
            value = str(state.enabled).lower()
            self.stdout.write(f"{state.name}={value} source={state.source}")
