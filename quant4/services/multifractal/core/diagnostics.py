"""Aggregate MF-DFA diagnostic reports for Quant4 research."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from quant4.services.multifractal.core.diagnostic_types import (
    BootstrapIntervalReport,
    ExtremeValueSensitivityReport,
    FiniteSizeReport,
    MetricComparison,
)
from quant4.services.multifractal.core.stat_tests import (
    bootstrap_confidence_intervals,
    run_broad_distribution_check,
    run_extreme_value_sensitivity,
    run_finite_size_check,
    run_shuffled_comparison,
    run_surrogate_comparison,
)
from quant4.services.multifractal.core.types import MFDFAConfig

JsonValue = dict[str, object]
ATTRIBUTIONS = (
    "likely_correlation_driven",
    "likely_distribution_driven",
    "likely_finite_size_artifact",
    "likely_extreme_value_dominated",
    "robust_multifractal_evidence",
    "inconclusive",
)


@dataclass(frozen=True, slots=True)
class MultifractalDiagnosticReport:
    """JSON and Markdown diagnostic report for one MF-DFA series.

    Example:
        `report = run_multifractal_diagnostics(series, config, seed=7)`
    """

    config: MFDFAConfig
    comparisons: dict[str, MetricComparison]
    finite_size: FiniteSizeReport
    extreme_value: ExtremeValueSensitivityReport
    bootstrap: BootstrapIntervalReport
    attribution: str
    warnings: tuple[str, ...]

    def to_json_dict(self) -> JsonValue:
        """Return a JSON-serializable diagnostic report.

        Example:
            `payload = report.to_json_dict()`
        """
        return {
            "config": _config_payload(self.config),
            "comparisons": {
                key: value.to_json_dict() for key, value in self.comparisons.items()
            },
            "finite_size": self.finite_size.to_json_dict(),
            "extreme_value": self.extreme_value.to_json_dict(),
            "bootstrap": self.bootstrap.to_json_dict(),
            "attribution": self.attribution,
            "warnings": list(self.warnings),
            "interpretation_caution": _interpretation_caution(),
        }

    def to_markdown(self) -> str:
        """Return a human-readable Markdown diagnostic report.

        Example:
            `markdown = report.to_markdown()`
        """
        lines = [
            "# Multifractal Diagnostics",
            "",
            f"- Attribution: `{self.attribution}`",
            f"- q grid: `{list(self.config.q_grid)}`",
            f"- scales: `{list(self.config.scales or [])}`",
            f"- warnings: `{list(self.warnings)}`",
            "",
            "## Comparisons",
            *_comparison_lines(self.comparisons),
            "",
            "## Bootstrap Intervals",
            *_bootstrap_lines(self.bootstrap),
            "",
            "## Caution",
            _interpretation_caution(),
        ]
        return "\n".join(lines)


def run_multifractal_diagnostics(
    series: Sequence[float],
    config: MFDFAConfig,
    seed: int,
    bootstrap_count: int = 50,
    finite_size_simulations: int = 10,
) -> MultifractalDiagnosticReport:
    """Run Phase 4 MF-DFA diagnostic checks for one local series.

    Example:
        `report = run_multifractal_diagnostics(series, config, seed=7)`
    """
    comparisons = _comparison_suite(series, config, seed)
    finite_size = run_finite_size_check(
        series,
        config,
        seed + 101,
        finite_size_simulations,
    )
    extreme_value = run_extreme_value_sensitivity(series, config)
    bootstrap = bootstrap_confidence_intervals(
        series,
        config,
        seed + 202,
        bootstrap_count,
    )
    attribution = attribute_multifractality(comparisons, finite_size, extreme_value)
    warnings = _collect_report_warnings(
        comparisons,
        finite_size,
        extreme_value,
        bootstrap,
    )
    return MultifractalDiagnosticReport(
        config,
        comparisons,
        finite_size,
        extreme_value,
        bootstrap,
        attribution,
        warnings,
    )


def attribute_multifractality(
    comparisons: dict[str, MetricComparison],
    finite_size: FiniteSizeReport,
    extreme_value: ExtremeValueSensitivityReport,
) -> str:
    """Classify likely multifractality attribution without validity claims.

    Example:
        `label = attribute_multifractality(comparisons, finite, extreme)`
    """
    if _finite_size_dominates(finite_size):
        return "likely_finite_size_artifact"
    if extreme_value.sensitivity_score > 0.25:
        return "likely_extreme_value_dominated"
    if comparisons["shuffled"].ratio_metrics["delta_alpha"] < 0.8:
        return "likely_correlation_driven"
    if comparisons["broad_distribution"].ratio_metrics["delta_alpha"] >= 0.8:
        return "likely_distribution_driven"
    if finite_size.delta_alpha_excess > 0.0:
        return "robust_multifractal_evidence"
    return "inconclusive"


def _comparison_suite(
    series: Sequence[float],
    config: MFDFAConfig,
    seed: int,
) -> dict[str, MetricComparison]:
    return {
        "shuffled": run_shuffled_comparison(series, config, seed),
        "surrogate_phase": run_surrogate_comparison(series, config, seed + 1),
        "broad_distribution": run_broad_distribution_check(series, config, seed + 2),
    }


def _finite_size_dominates(report: FiniteSizeReport) -> bool:
    return report.is_short_sample and report.delta_alpha_excess <= 0.0


def _collect_report_warnings(
    comparisons: dict[str, MetricComparison],
    finite_size: FiniteSizeReport,
    extreme_value: ExtremeValueSensitivityReport,
    bootstrap: BootstrapIntervalReport,
) -> tuple[str, ...]:
    warnings: list[str] = []
    for comparison in comparisons.values():
        warnings.extend(comparison.warnings)
    warnings.extend(finite_size.warnings)
    warnings.extend(extreme_value.warnings)
    warnings.extend(bootstrap.warnings)
    return tuple(dict.fromkeys(warnings))


def _comparison_lines(comparisons: dict[str, MetricComparison]) -> list[str]:
    return [
        "- "
        f"{name}: delta_alpha_ratio="
        f"{comparison.ratio_metrics['delta_alpha']:.4f}"
        for name, comparison in comparisons.items()
    ]


def _bootstrap_lines(report: BootstrapIntervalReport) -> list[str]:
    return [
        f"- {metric}: [{bounds[0]:.6f}, {bounds[1]:.6f}]"
        for metric, bounds in report.intervals.items()
    ]


def _config_payload(config: MFDFAConfig) -> JsonValue:
    return {
        "q_grid": list(config.q_grid),
        "scales": list(config.scales or []),
        "detrending_order": config.detrending_order,
        "use_reverse_segments": config.use_reverse_segments,
        "robust_regression": config.robust_regression,
    }


def _interpretation_caution() -> str:
    return (
        "Diagnostics describe scaling evidence and sensitivity checks only; "
        "they do not validate factor profitability or trading suitability."
    )
