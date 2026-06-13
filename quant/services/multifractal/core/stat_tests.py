"""Statistical diagnostics for Quant MF-DFA outputs."""

from __future__ import annotations

import math
import random
from collections.abc import Sequence

from quant.services.multifractal.core.diagnostic_types import (
    BootstrapIntervalReport,
    ExtremeValueSensitivityReport,
    FiniteSizeReport,
    MetricComparison,
)
from quant.services.multifractal.core.mfdfa import run_mfdfa
from quant.services.multifractal.core.types import MFDFAConfig, MFDFAResult
from quant.services.multifractal.preprocessing.outliers import winsorize_values
from quant.services.multifractal.preprocessing.surrogates import (
    bootstrap_sample,
    iaaft_surrogate,
    phase_randomized_surrogate,
    shuffled_returns,
)

METRIC_KEYS = ("hurst_h2", "delta_alpha", "alpha_peak", "spectrum_asymmetry")
FINITE_SIZE_WARNING_LENGTH = 128


def run_shuffled_comparison(
    series: Sequence[float],
    config: MFDFAConfig,
    seed: int,
    shuffle_count: int = 5,
) -> MetricComparison:
    """Compare original MF-DFA metrics against shuffled returns.

    Example:
        `comparison = run_shuffled_comparison(series, config, seed=7)`
    """
    values = _finite_series(series)
    controls = [
        shuffled_returns(values, seed + index) for index in range(shuffle_count)
    ]
    return _comparison_from_controls(values, controls, config, "shuffled")


def run_surrogate_comparison(
    series: Sequence[float],
    config: MFDFAConfig,
    seed: int,
    method: str = "phase",
) -> MetricComparison:
    """Compare original MF-DFA metrics against phase or IAAFT surrogates.

    Example:
        `comparison = run_surrogate_comparison(series, config, 7, "phase")`
    """
    values = _finite_series(series)
    control = _surrogate_values(values, seed, method)
    return _comparison_from_controls(values, [control], config, f"surrogate_{method}")


def run_broad_distribution_check(
    series: Sequence[float],
    config: MFDFAConfig,
    seed: int,
) -> MetricComparison:
    """Compare against a heavy-tail-preserving shuffled control.

    Example:
        `report = run_broad_distribution_check(series, config, seed=7)`
    """
    values = _finite_series(series)
    control = shuffled_returns(values, seed)
    return _comparison_from_controls(
        values,
        [control],
        config,
        "broad_distribution_shuffle",
    )


def run_finite_size_check(
    series: Sequence[float],
    config: MFDFAConfig,
    seed: int,
    simulation_count: int = 10,
) -> FiniteSizeReport:
    """Compare original MF-DFA metrics with same-length Gaussian controls.

    Example:
        `report = run_finite_size_check(series, config, seed=7, simulation_count=5)`
    """
    values = _finite_series(series)
    _validate_positive_int(simulation_count, "simulation_count")
    original_metrics = _mfdfa_metrics(values, config)
    controls = _finite_size_controls(values, seed, simulation_count)
    control_metrics = [_mfdfa_metrics(control, config) for control in controls]
    means = _mean_metrics(control_metrics)
    warnings = _finite_size_warnings(values, original_metrics, means)
    return FiniteSizeReport(
        len(values),
        len(values) < FINITE_SIZE_WARNING_LENGTH,
        original_metrics,
        means,
        _std_metrics(control_metrics, means),
        original_metrics["delta_alpha"] - means["delta_alpha"],
        warnings,
    )


def run_extreme_value_sensitivity(
    series: Sequence[float],
    config: MFDFAConfig,
    lower_quantile: float = 0.05,
    upper_quantile: float = 0.95,
    method: str = "winsorized",
) -> ExtremeValueSensitivityReport:
    """Rerun MF-DFA after explicit extreme-value adjustment.

    Example:
        `report = run_extreme_value_sensitivity(series, config)`
    """
    values = _finite_series(series)
    adjusted = _adjust_extremes(values, lower_quantile, upper_quantile, method)
    original = _mfdfa_metrics(values, config)
    adjusted_metrics = _mfdfa_metrics(adjusted, config)
    sensitivity = _metric_distance(original, adjusted_metrics)
    return ExtremeValueSensitivityReport(
        method,
        len(values),
        len(adjusted),
        original,
        adjusted_metrics,
        sensitivity,
        _extreme_warnings(sensitivity),
    )


def bootstrap_confidence_intervals(
    series: Sequence[float],
    config: MFDFAConfig,
    seed: int,
    bootstrap_count: int = 50,
    confidence_level: float = 0.95,
) -> BootstrapIntervalReport:
    """Estimate seeded bootstrap confidence intervals for MF-DFA metrics.

    Example:
        `intervals = bootstrap_confidence_intervals(series, config, 7, 20)`
    """
    values = _finite_series(series)
    _validate_positive_int(bootstrap_count, "bootstrap_count")
    _validate_confidence(confidence_level)
    estimates = _bootstrap_metric_estimates(values, config, seed, bootstrap_count)
    intervals = _confidence_intervals(estimates, confidence_level)
    return BootstrapIntervalReport(
        seed,
        bootstrap_count,
        intervals,
        estimates,
        _bootstrap_warnings(bootstrap_count),
    )


def _comparison_from_controls(
    values: Sequence[float],
    controls: Sequence[Sequence[float]],
    config: MFDFAConfig,
    method: str,
) -> MetricComparison:
    original = _mfdfa_metrics(values, config)
    comparison = _mean_metrics(
        [_mfdfa_metrics(control, config) for control in controls]
    )
    return MetricComparison(
        method,
        original,
        comparison,
        _delta_metrics(original, comparison),
        _ratio_metrics(original, comparison),
        tuple(),
    )


def _mfdfa_metrics(values: Sequence[float], config: MFDFAConfig) -> dict[str, float]:
    result = run_mfdfa(values, config)
    return _metrics_from_result(result)


def _metrics_from_result(result: MFDFAResult) -> dict[str, float]:
    mean_r2 = sum(result.scaling_r2_by_q.values()) / len(result.scaling_r2_by_q)
    return {
        "hurst_h2": result.spectrum.hurst_h2,
        "delta_alpha": result.spectrum.delta_alpha,
        "alpha_peak": result.spectrum.alpha_peak,
        "spectrum_asymmetry": result.spectrum.spectrum_asymmetry,
        "scaling_quality_mean_r2": mean_r2,
    }


def _finite_size_controls(
    values: Sequence[float],
    seed: int,
    simulation_count: int,
) -> list[list[float]]:
    chooser = random.Random(seed)
    center = _mean(values)
    scale = _std(values) or 1.0
    return [
        [chooser.gauss(center, scale) for _index in range(len(values))]
        for _sample in range(simulation_count)
    ]


def _bootstrap_metric_estimates(
    values: Sequence[float],
    config: MFDFAConfig,
    seed: int,
    bootstrap_count: int,
) -> dict[str, tuple[float, ...]]:
    estimates: dict[str, list[float]] = {key: [] for key in METRIC_KEYS}
    for offset in range(bootstrap_count):
        sample = bootstrap_sample(values, len(values), seed + offset)
        _append_metric_estimate(estimates, _mfdfa_metrics(sample, config))
    return {key: tuple(metric_values) for key, metric_values in estimates.items()}


def _append_metric_estimate(
    estimates: dict[str, list[float]],
    metrics: dict[str, float],
) -> None:
    for key in METRIC_KEYS:
        estimates[key].append(metrics[key])


def _confidence_intervals(
    estimates: dict[str, tuple[float, ...]],
    confidence_level: float,
) -> dict[str, tuple[float, float]]:
    tail = (1.0 - confidence_level) / 2.0
    return {
        key: (_percentile(values, tail), _percentile(values, 1.0 - tail))
        for key, values in estimates.items()
    }


def _surrogate_values(values: Sequence[float], seed: int, method: str) -> list[float]:
    if method == "phase":
        return phase_randomized_surrogate(values, seed)
    if method == "iaaft":
        return iaaft_surrogate(values, seed)
    raise ValueError(f"Invalid surrogate method {method!r}; expected phase or iaaft")


def _adjust_extremes(
    values: Sequence[float],
    lower_quantile: float,
    upper_quantile: float,
    method: str,
) -> list[float]:
    if method == "winsorized":
        return winsorize_values(values, lower_quantile, upper_quantile)
    if method == "masked":
        return _mask_extremes(values, lower_quantile, upper_quantile)
    raise ValueError(
        f"Invalid extreme method {method!r}; expected winsorized or masked"
    )


def _mask_extremes(
    values: Sequence[float],
    lower_quantile: float,
    upper_quantile: float,
) -> list[float]:
    lower = _percentile(values, lower_quantile)
    upper = _percentile(values, upper_quantile)
    median = _percentile(values, 0.5)
    return [median if value < lower or value > upper else value for value in values]


def _finite_size_warnings(
    values: Sequence[float],
    original: dict[str, float],
    synthetic: dict[str, float],
) -> tuple[str, ...]:
    warnings: list[str] = []
    if len(values) < FINITE_SIZE_WARNING_LENGTH:
        warnings.append("finite_size_warning")
    if original["delta_alpha"] <= synthetic["delta_alpha"]:
        warnings.append("synthetic_width_not_exceeded")
    return tuple(warnings)


def _extreme_warnings(sensitivity: float) -> tuple[str, ...]:
    if sensitivity > 0.25:
        return ("extreme_value_sensitive",)
    return tuple()


def _bootstrap_warnings(bootstrap_count: int) -> tuple[str, ...]:
    if bootstrap_count < 20:
        return ("wide_interval_possible",)
    return tuple()


def _delta_metrics(
    original: dict[str, float],
    comparison: dict[str, float],
) -> dict[str, float]:
    return {key: comparison[key] - original[key] for key in comparison}


def _ratio_metrics(
    original: dict[str, float],
    comparison: dict[str, float],
) -> dict[str, float]:
    return {key: _safe_ratio(comparison[key], original[key]) for key in comparison}


def _mean_metrics(metrics: Sequence[dict[str, float]]) -> dict[str, float]:
    keys = metrics[0].keys()
    return {key: sum(item[key] for item in metrics) / len(metrics) for key in keys}


def _std_metrics(
    metrics: Sequence[dict[str, float]],
    means: dict[str, float],
) -> dict[str, float]:
    return {
        key: math.sqrt(
            sum((item[key] - means[key]) ** 2 for item in metrics) / len(metrics)
        )
        for key in means
    }


def _metric_distance(left: dict[str, float], right: dict[str, float]) -> float:
    return sum(abs(left[key] - right[key]) for key in METRIC_KEYS) / len(METRIC_KEYS)


def _safe_ratio(numerator: float, denominator: float) -> float:
    if denominator == 0.0:
        return 0.0 if numerator == 0.0 else math.inf
    return numerator / denominator


def _finite_series(series: Sequence[float]) -> list[float]:
    if not series:
        raise ValueError(f"Invalid series {series!r}; expected finite numeric series")
    return [_finite_float(value) for value in series]


def _finite_float(value: object) -> float:
    try:
        parsed = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(
            f"Invalid series value {value!r}; expected finite numeric series"
        ) from exc
    if math.isfinite(parsed):
        return parsed
    raise ValueError(f"Invalid series value {value!r}; expected finite numeric series")


def _validate_positive_int(value: int, label: str) -> None:
    if isinstance(value, int) and value > 0:
        return
    raise ValueError(f"Invalid {label} {value!r}; expected positive integer")


def _validate_confidence(value: float) -> None:
    if 0.0 < value < 1.0:
        return
    raise ValueError(f"Invalid confidence_level {value!r}; expected float in (0, 1)")


def _mean(values: Sequence[float]) -> float:
    return sum(values) / len(values)


def _std(values: Sequence[float]) -> float:
    center = _mean(values)
    return math.sqrt(sum((value - center) ** 2 for value in values) / len(values))


def _percentile(values: Sequence[float], quantile: float) -> float:
    ordered = sorted(values)
    position = quantile * (len(ordered) - 1)
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return ordered[lower]
    return ordered[lower] + (ordered[upper] - ordered[lower]) * (position - lower)
