"""Risk report rendering for Quant multifractal diagnostics."""

from __future__ import annotations

from dataclasses import dataclass

from quant.services.multifractal.risk.multifractal_risk import (
    MultifractalRiskAssessment,
)
from quant.services.multifractal.risk.stress import (
    apply_stress_scenarios,
    scenario_summary,
)


@dataclass(frozen=True, slots=True)
class MultifractalRiskReport:
    """JSON and Markdown risk report.

    Example:
        `report = build_risk_report("SPY", assessment)`
    """

    symbol: str
    sections: dict[str, object]
    caution: str

    def to_json_dict(self) -> dict[str, object]:
        """Return a JSON-serializable risk report."""
        return {
            "symbol": self.symbol,
            "sections": self.sections,
            "caution": self.caution,
        }

    def to_markdown(self) -> str:
        """Return a Markdown risk report."""
        return "\n".join(
            [
                "# Multifractal Risk Report",
                "",
                f"- Symbol: `{self.symbol}`",
                f"- Risk score: `{self.sections['risk_score']}`",
                "",
                "This is not a prediction and not investment advice.",
            ]
        )


def build_risk_report(
    symbol: str,
    assessment: MultifractalRiskAssessment,
) -> MultifractalRiskReport:
    """Build separated risk report sections.

    Example:
        `report = build_risk_report("SPY", assessment)`
    """
    sections = assessment.to_json_dict()
    stress_outputs = apply_stress_scenarios(assessment.risk_score)
    sections["stress_scenarios"] = stress_outputs
    sections["stress_summary"] = scenario_summary(stress_outputs)
    return MultifractalRiskReport(symbol, sections, _caution())


def _caution() -> str:
    return "Risk diagnostics are not a prediction, causality claim, or trading signal."
