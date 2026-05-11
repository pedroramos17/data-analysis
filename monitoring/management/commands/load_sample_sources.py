"""Load sample source registry entries."""

import json
from pathlib import Path
from typing import cast

from django.core.management.base import BaseCommand

from monitoring.models import Source


class Command(BaseCommand):
    """Load bundled sample sources into the registry.

    Example:
        `python manage.py load_sample_sources`
    """

    help = "Load sample sources from sample_data/sources.json."

    def handle(self, *args: object, **options: object) -> None:
        """Create or update bundled sample sources.

        Example:
            Django calls this after parsing command options.
        """
        sample_path = Path("sample_data") / "sources.json"
        source_rows = _load_source_rows(sample_path)
        for row in source_rows:
            source_name = str(row["name"])
            Source.objects.update_or_create(name=source_name, defaults=row)
        self.stdout.write(f"Loaded {len(source_rows)} sample sources")


def _load_source_rows(path: Path) -> list[dict[str, object]]:
    with path.open(encoding="utf-8") as source_file:
        payload = json.load(source_file)
    if not isinstance(payload, list):
        raise ValueError(f"Invalid sample source file {path!s}; expected list")
    return [cast(dict[str, object], row) for row in payload]
