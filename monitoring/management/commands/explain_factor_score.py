"""Explain one symbolic factor score."""

from django.core.management.base import BaseCommand, CommandParser
from django.db import connection

from sourceflow.intelligence.factor_base.registry import FactorRegistry
from sourceflow.intelligence.symbolic.expression import formula_text
from sourceflow.intelligence.xai.explain_factor import explain_factor_score


class Command(BaseCommand):
    """Print a neutral factor score explanation."""

    help = "Explain one Sourceflow factor score without truth judgments."

    def add_arguments(self, parser: CommandParser) -> None:
        """Add explanation options.

        Example:
            Django calls this before command execution.
        """
        parser.add_argument("--factor", default="coverage_intensity")
        parser.add_argument("--entity-id", default="")
        parser.add_argument("--score", type=float, default=0.0)

    def handle(self, *args: object, **options: object) -> None:
        """Print a factor explanation.

        Example:
            `python manage.py explain_factor_score --factor coverage_intensity`
        """
        factor_name = str(options.get("factor") or "coverage_intensity")
        definition = FactorRegistry(connection).get_factor(factor_name, missing_ok=True)
        expression_text = _expression_text(definition, factor_name)
        explanation = explain_factor_score(
            factor_name,
            expression_text,
            float(options.get("score") or 0.0),
            dependencies=FactorRegistry(connection).factor_dependencies(factor_name),
        )
        self.stdout.write(explanation.summary)


def _expression_text(definition: object, factor_name: str) -> str:
    if definition is None:
        return factor_name
    return formula_text(definition.expression)
