"""Canonical command for registering Sourceflow seed factors."""

from django.core.management.base import BaseCommand
from django.db import connection

from sourceflow.intelligence.factor_base.registry import FactorRegistry
from sourceflow.intelligence.seeds import seed_factor_definitions


class Command(BaseCommand):
    """Register seed symbolic factors in SQLite."""

    help = "Register Sourceflow seed symbolic factors."

    def handle(self, *args: object, **options: object) -> None:
        """Run seed registration.

        Example:
            `python manage.py register_seed_factors`
        """
        count = FactorRegistry(connection).register_factors(seed_factor_definitions())
        self.stdout.write(f"Registered {count} seed factors")
