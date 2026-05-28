"""Initialize or upgrade the Sourceflow factor registry."""

from django.core.management.base import BaseCommand
from django.db import connection

from sourceflow.intelligence.factor_base.migrations_or_init import upgrade_factor_schema


class Command(BaseCommand):
    """Initialize the raw-SQL symbolic factor registry."""

    help = "Initialize or upgrade the Sourceflow symbolic factor registry."

    def handle(self, *args: object, **options: object) -> None:
        """Run registry initialization.

        Example:
            `python manage.py init_factor_base`
        """
        upgrade_factor_schema(connection)
        self.stdout.write("Initialized symbolic factor registry")
