"""Typed diagnostic report objects for Quant MF-DFA checks."""

from __future__ import annotations

from dataclasses import dataclass

JsonValue = dict[str, object]


@dataclass(frozen=True, slots=True)
class MetricComparison:
    """Original-vs-control MF-DFA metric comparison.

    Example:
        `comparison = run_shuffled_comparison(series, config, seed=7)`
    """

    method: str
    original_metrics: dict[str, float]
    comparison_metrics: dict[str, float]
    delta_metrics: dict[str, float]
    ratio_metrics: dict[str, float]
    warnings: tuple[str, ...]

    def to_json_dict(self) -> JsonValue:
        """Return a JSON-serializable comparison payload.

        Example:
            `payload = comparison.to_json_dict()`
        """
        return {
            "method": self.method,
            "original_metrics": self.original_metrics,
            "comparison_metrics": self.comparison_metrics,
            "delta_metrics": self.delta_metrics,
            "ratio_metrics": self.ratio_metrics,
            "warnings": list(self.warnings),
        }


@dataclass(frozen=True, slots=True)
class FiniteSizeReport:
    """Finite-size comparison against synthetic Gaussian controls.

    Example:
        `report = run_finite_size_check(series, config, seed=7)`
    """

    sample_length: int
    is_short_sample: bool
    original_metrics: dict[str, float]
    synthetic_metric_means: dict[str, float]
    synthetic_metric_stds: dict[str, float]
    delta_alpha_excess: float
    warnings: tuple[str, ...]

    def to_json_dict(self) -> JsonValue:
        """Return a JSON-serializable finite-size payload.

        Example:
            `payload = report.to_json_dict()`
        """
        return {
            "sample_length": self.sample_length,
            "is_short_sample": self.is_short_sample,
            "original_metrics": self.original_metrics,
            "synthetic_metric_means": self.synthetic_metric_means,
            "synthetic_metric_stds": self.synthetic_metric_stds,
            "synthetic_delta_alpha_mean": self.synthetic_metric_means["delta_alpha"],
            "delta_alpha_excess": self.delta_alpha_excess,
            "warnings": list(self.warnings),
        }


@dataclass(frozen=True, slots=True)
class BootstrapIntervalReport:
    """Bootstrap confidence intervals for MF-DFA summary metrics.

    Example:
        `intervals = bootstrap_confidence_intervals(series, config, 7, 20)`
    """

    seed: int
    bootstrap_count: int
    intervals: dict[str, tuple[float, float]]
    estimates: dict[str, tuple[float, ...]]
    warnings: tuple[str, ...]

    def to_json_dict(self) -> JsonValue:
        """Return a JSON-serializable bootstrap payload.

        Example:
            `payload = intervals.to_json_dict()`
        """
        return {
            "seed": self.seed,
            "bootstrap_count": self.bootstrap_count,
            "intervals": {
                key: [bounds[0], bounds[1]] for key, bounds in self.intervals.items()
            },
            "estimates": {
                key: list(values) for key, values in self.estimates.items()
            },
            "warnings": list(self.warnings),
        }


@dataclass(frozen=True, slots=True)
class ExtremeValueSensitivityReport:
    """MF-DFA sensitivity after explicit extreme-value adjustment.

    Example:
        `report = run_extreme_value_sensitivity(series, config)`
    """

    method: str
    original_count: int
    adjusted_count: int
    original_metrics: dict[str, float]
    adjusted_metrics: dict[str, float]
    sensitivity_score: float
    warnings: tuple[str, ...]

    def to_json_dict(self) -> JsonValue:
        """Return a JSON-serializable extreme sensitivity payload.

        Example:
            `payload = report.to_json_dict()`
        """
        return {
            "method": self.method,
            "original_count": self.original_count,
            "adjusted_count": self.adjusted_count,
            "original_metrics": self.original_metrics,
            "adjusted_metrics": self.adjusted_metrics,
            "sensitivity_score": self.sensitivity_score,
            "warnings": list(self.warnings),
        }
