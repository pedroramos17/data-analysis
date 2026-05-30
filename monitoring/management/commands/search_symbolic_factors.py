"""Search Sourceflow symbolic formulas."""

from __future__ import annotations

from pathlib import Path

import pandas as pd
from django.conf import settings
from django.core.management.base import BaseCommand, CommandParser
from django.utils import timezone

from sourceflow.intelligence.factor_base.storage import FactorValueStorage
from sourceflow.intelligence.search.constraints import SearchConstraints
from sourceflow.intelligence.search.genetic_programming import run_genetic_search
from sourceflow.intelligence.search.random_search import run_random_search
from sourceflow.intelligence.symbolic.compiler import FactorExecutionContext


class Command(BaseCommand):
    """Generate and evaluate symbolic candidate formulas."""

    help = "Search grammar-constrained symbolic formulas."

    def add_arguments(self, parser: CommandParser) -> None:
        """Add search options.

        Example:
            Django calls this before command execution.
        """
        parser.add_argument("--method", default="random")
        parser.add_argument("--count", type=int, default=500)
        parser.add_argument("--n", type=int, default=0)
        parser.add_argument("--max-depth", type=int, default=4)
        parser.add_argument("--max-operators", type=int, default=12)
        parser.add_argument("--objective", default="future_event_growth")
        parser.add_argument("--window", default="7d")
        parser.add_argument("--population", type=int, default=100)
        parser.add_argument("--generations", type=int, default=20)
        parser.add_argument("--seed", type=int, default=1)

    def handle(self, *args: object, **options: object) -> None:
        """Run random or GP symbolic search.

        Example:
            `python manage.py search_symbolic_factors --method random --n 500`
        """
        constraints = _constraints(options)
        context = _execution_context()
        if str(options.get("method", "random")) == "gp":
            result = _run_gp(options, constraints, context)
            self.stdout.write(
                f"Completed {result.generations_completed} GP generations"
            )
            return
        result = _run_random(options, constraints, context)
        self.stdout.write(
            f"Generated {result.generated_count}; accepted {result.accepted_count}"
        )


def _constraints(options: dict[str, object]) -> SearchConstraints:
    return SearchConstraints(
        max_depth=int(options.get("max_depth") or 4),
        max_operators=int(options.get("max_operators") or 12),
    )


def _run_random(
    options: dict[str, object],
    constraints: SearchConstraints,
    context: FactorExecutionContext,
) -> object:
    count = int(options.get("n") or options.get("count") or 500)
    return run_random_search(
        count,
        constraints,
        context,
        str(options.get("objective") or "future_event_growth"),
        int(options.get("seed") or 1),
    )


def _run_gp(
    options: dict[str, object],
    constraints: SearchConstraints,
    context: FactorExecutionContext,
) -> object:
    return run_genetic_search(
        int(options.get("population") or 100),
        int(options.get("generations") or 20),
        constraints,
        context,
        str(options.get("objective") or "future_event_growth"),
        int(options.get("seed") or 1),
    )


def _execution_context() -> FactorExecutionContext:
    export_dir = Path(settings.PARQUET_EXPORT_DIR)
    storage = FactorValueStorage(export_dir / "factors")
    frame = _factor_frame(storage)
    now = timezone.now()
    return FactorExecutionContext(now, now, now, frame, storage, export_dir)


def _factor_frame(storage: FactorValueStorage) -> pd.DataFrame:
    path = storage.latest_path("coverage_intensity")
    if path is None:
        return _fallback_frame()
    rows = storage.read_values(path)
    if not rows:
        return _fallback_frame()
    return _rows_to_frame(rows)


def _rows_to_frame(rows: list[dict[str, object]]) -> pd.DataFrame:
    frame = pd.DataFrame(rows)
    values = pd.to_numeric(frame.get("value", 0), errors="coerce").fillna(0)
    frame["article_count"] = values
    frame["event_source_count"] = values.rank(method="first")
    frame["evidence_span_count"] = values.abs() + 1
    return frame


def _fallback_frame() -> pd.DataFrame:
    now = timezone.now()
    return pd.DataFrame(
        {
            "entity_id": ("event:1", "event:2"),
            "event_id": (1, 2),
            "source_id": (1, 2),
            "provider": ("fallback-a", "fallback-b"),
            "as_of": (now, now),
            "article_count": (1.0, 2.0),
            "event_source_count": (1.0, 2.0),
            "evidence_span_count": (1.0, 3.0),
        }
    )
