"""Markdown and JSON reports for Quant4 multifractal research."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass

from quant4.services.multifractal.core.diagnostics import run_multifractal_diagnostics
from quant4.services.multifractal.core.mfdfa import run_mfdfa
from quant4.services.multifractal.core.types import MFDFAConfig
from quant4.services.multifractal.portfolio.multifractal_optimizer import (
    optimize_multifractal_adjusted_portfolio,
)
from quant4.services.multifractal.regime.multifractal_regime import (
    detect_multifractal_regimes,
)
from quant4.services.multifractal.risk.multifractal_risk import (
    compute_asset_multifractal_risk,
)


@dataclass(frozen=True, slots=True)
class MultifractalResearchReport:
    """Research report that does not claim predictive performance.

    Example:
        `markdown = report.to_markdown()`
    """

    symbol: str
    dataset_id: str
    config: MFDFAConfig
    sections: Mapping[str, object]
    warnings: tuple[str, ...]

    def to_json_dict(self) -> dict[str, object]:
        """Return a JSON-serializable report payload."""
        return {
            "symbol": self.symbol,
            "dataset_id": self.dataset_id,
            "config": asdict(self.config),
            "sections": dict(self.sections),
            "warnings": list(self.warnings),
            "claims_predictive_performance": False,
        }

    def to_markdown(self) -> str:
        """Render the report as Markdown."""
        return "\n".join(_markdown_lines(self))


def build_multifractal_research_report(
    symbol: str,
    dataset_id: str,
    series: Sequence[float],
    config: MFDFAConfig | None = None,
) -> MultifractalResearchReport:
    """Build a complete local multifractal research report.

    Example:
        `report = build_multifractal_research_report("SPY", "dataset", returns)`
    """
    active_config = config or MFDFAConfig()
    mfdfa = run_mfdfa(series, active_config)
    diagnostics = run_multifractal_diagnostics(
        series,
        active_config,
        seed=17,
        bootstrap_count=4,
        finite_size_simulations=2,
    )
    sections = _sections(symbol, series, mfdfa.summary, diagnostics.attribution)
    return MultifractalResearchReport(
        symbol=symbol,
        dataset_id=dataset_id,
        config=active_config,
        sections=sections,
        warnings=mfdfa.warnings + diagnostics.warnings,
    )


def _sections(
    symbol: str,
    series: Sequence[float],
    mfdfa_summary: Mapping[str, object],
    attribution: str,
) -> dict[str, object]:
    risk = compute_asset_multifractal_risk(series, {"delta_alpha": 0.2})
    regimes = detect_multifractal_regimes(_regime_rows(series))
    portfolio = optimize_multifractal_adjusted_portfolio(
        [symbol],
        [[max(risk.risk_score, 1e-6)]],
        {},
    )
    return {
        "data_summary": {"observation_count": len(series)},
        "mfdfa_summary": dict(mfdfa_summary),
        "diagnostics": {"attribution": attribution},
        "risk": risk.to_json_dict(),
        "regime": regimes.to_json_dict(),
        "portfolio": portfolio.to_json_dict(),
    }


def _markdown_lines(report: MultifractalResearchReport) -> list[str]:
    sections = report.sections
    return [
        "# Multifractal Research Report",
        "",
        "## Data Summary",
        f"- Symbol: `{report.symbol}`",
        f"- Dataset ID: `{report.dataset_id}`",
        f"- Observations: `{sections['data_summary']['observation_count']}`",
        "",
        "## MF-DFA Summary",
        "- Method: `mfdfa`",
        f"- q grid: `{list(report.config.q_grid)}`",
        f"- scale range: `{(report.config.min_scale, report.config.max_scale)}`",
        f"- H(2): `{sections['mfdfa_summary'].get('hurst_h2')}`",
        "",
        "## Diagnostics",
        f"- Attribution: `{sections['diagnostics']['attribution']}`",
        f"- Warnings: `{list(report.warnings)}`",
        "",
        "## Risk",
        f"- Risk score: `{sections['risk']['risk_score']}`",
        "",
        "## Regime",
        "- Latest labels are research diagnostics only.",
        "",
        "## Portfolio Notes",
        "- Allocation output is research-only and has no execution path.",
        "",
        "## Interpretation Cautions",
        "- This report is not a prediction, trading signal, or validity claim.",
    ]


def _regime_rows(series: Sequence[float]) -> list[dict[str, float]]:
    return [
        {
            "hurst_h2": 0.5,
            "delta_alpha": abs(float(value)),
            "spectrum_asymmetry": float(value),
            "tau_nonlinearity": abs(float(value)),
            "realized_volatility": abs(float(value)),
            "drawdown": min(0.0, float(value)),
        }
        for value in series
    ]
