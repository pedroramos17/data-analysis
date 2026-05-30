"""Evaluate Sourceflow symbolic factor values."""

from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandParser
from django.db import connection

from sourceflow.intelligence.evaluation.forward_validation import (
    evaluate_forward_window,
)
from sourceflow.intelligence.factor_base.registry import FactorRegistry
from sourceflow.intelligence.factor_base.storage import FactorValueStorage


class Command(BaseCommand):
    """Evaluate persisted symbolic factor values."""

    help = "Evaluate Sourceflow symbolic factors with forward validation."

    def add_arguments(self, parser: CommandParser) -> None:
        """Add evaluation options.

        Example:
            Django calls this before command execution.
        """
        parser.add_argument("--objective", default="future_event_growth")
        parser.add_argument("--factor", default="coverage_intensity")

    def handle(self, *args: object, **options: object) -> None:
        """Run forward validation against persisted factor values.

        Example:
            `python manage.py evaluate_symbolic_factors --objective future_event_growth`
        """
        factor_name = str(options.get("factor") or "coverage_intensity")
        objective = str(options.get("objective") or "future_event_growth")
        rows = _evaluation_rows(factor_name, objective)
        if rows:
            FactorRegistry(connection).record_factor_evaluation(
                evaluate_forward_window(rows, objective)
            )
        self.stdout.write(f"Evaluated {len(rows)} symbolic factor rows")


def _evaluation_rows(factor_name: str, objective: str) -> list[dict[str, object]]:
    storage = FactorValueStorage(Path(settings.PARQUET_EXPORT_DIR) / "factors")
    path = storage.latest_path(factor_name)
    if path is None:
        return []
    return [
        _evaluation_row(row, factor_name, objective)
        for row in storage.read_values(path)
        if objective in row
    ]


def _evaluation_row(
    row: dict[str, object],
    factor_name: str,
    objective: str,
) -> dict[str, object]:
    value = float(row.get("value", 0) or 0)
    return {
        "entity_id": row.get("entity_id", ""),
        "as_of": row.get("as_of", ""),
        factor_name: value,
        objective: float(row.get(objective, 0) or 0),
    }
