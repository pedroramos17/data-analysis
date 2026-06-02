"""Shared helpers for Quant4 multifractal method implementations."""

from __future__ import annotations

import math
from collections.abc import Sequence

from quant4.services.multifractal.core.scaling import (
    build_scaling_diagnostic,
    default_scale_grid,
)
from quant4.services.multifractal.core.spectrum import (
    build_multifractal_spectrum,
    q_label,
)
from quant4.services.multifractal.core.types import (
    MFDFAConfig,
    MultifractalMethodResult,
    MultifractalSpectrum,
    ScalingDiagnostics,
    SummaryValue,
)


def finite_series(series: Sequence[float], label: str = "series") -> list[float]:
    """Coerce a sequence into finite floats.

    Example:
        `values = finite_series([1.0, 2.0])`
    """
    if not series:
        raise ValueError(f"Invalid {label} {series!r}; expected finite numeric series")
    return [_finite_float(value, label) for value in series]


def positive_measure(series: Sequence[float]) -> list[float]:
    """Coerce a sequence into a strictly positive measure.

    Example:
        `measure = positive_measure([1.0, 2.0])`
    """
    values = finite_series(series, "measure")
    for value in values:
        if value > 0.0:
            continue
        raise ValueError(
            f"Invalid measure value {value!r}; expected positive measure"
        )
    return values


def centered_profile(values: Sequence[float]) -> list[float]:
    """Return the cumulative centered profile used by scaling methods.

    Example:
        `profile = centered_profile([0.1, -0.2, 0.3])`
    """
    center = mean(values)
    cumulative = 0.0
    profile: list[float] = []
    for value in values:
        cumulative += value - center
        profile.append(cumulative)
    return profile


def resolve_method_scales(
    length: int,
    config: MFDFAConfig,
    method: str,
) -> tuple[int, ...]:
    """Resolve and validate scale grids for non-MF-DFA methods.

    Example:
        `scales = resolve_method_scales(256, config, "mfdma")`
    """
    validate_method_config(config)
    scales = _configured_or_default_scales(length, config)
    _validate_scale_count(scales, config, method)
    for scale in scales:
        _validate_scale(scale, length, config, method)
    return scales


def build_method_result(
    method: str,
    config: MFDFAConfig,
    scales: Sequence[int],
    fluctuation_functions: dict[str, tuple[tuple[int, float], ...]],
    metadata: dict[str, SummaryValue],
    warnings: tuple[str, ...] = tuple(),
) -> MultifractalMethodResult:
    """Build a common multifractal method result from q fluctuation functions.

    Example:
        `result = build_method_result("mfdma", config, scales, functions, {})`
    """
    diagnostics = {
        label: build_scaling_diagnostic(
            points,
            float(label),
            config.robust_regression,
            config.min_scale,
            config.max_scale,
            config.min_scale_count,
        )
        for label, points in fluctuation_functions.items()
    }
    hq = {label: diagnostic.slope for label, diagnostic in diagnostics.items()}
    spectrum = build_multifractal_spectrum(config.q_grid, hq)
    summary = method_summary(spectrum, diagnostics)
    return MultifractalMethodResult(
        method,
        config,
        tuple(float(value) for value in config.q_grid),
        tuple(scales),
        fluctuation_functions,
        spectrum,
        diagnostics,
        {label: diagnostic.r_squared for label, diagnostic in diagnostics.items()},
        min(diagnostic.scale_count for diagnostic in diagnostics.values()),
        summary,
        warnings + _diagnostic_warnings(diagnostics),
        metadata,
    )


def method_summary(
    spectrum: object,
    diagnostics: object,
) -> dict[str, SummaryValue]:
    """Return summary metrics shared by multifractal method outputs.

    Example:
        `summary = method_summary(result.spectrum, result.diagnostics_by_q)`
    """
    typed_spectrum = _typed_spectrum(spectrum)
    typed_diagnostics = _typed_diagnostics(diagnostics)
    mean_r2 = sum(item.r_squared for item in typed_diagnostics.values())
    return {
        "hurst_h2": typed_spectrum.hurst_h2,
        "delta_alpha": typed_spectrum.delta_alpha,
        "alpha_peak": typed_spectrum.alpha_peak,
        "spectrum_width": typed_spectrum.spectrum_width,
        "spectrum_asymmetry": typed_spectrum.spectrum_asymmetry,
        "hq_range": typed_spectrum.hq_range,
        "tau_nonlinearity": typed_spectrum.tau_nonlinearity,
        "scaling_quality_mean_r2": mean_r2 / len(typed_diagnostics),
        "valid_scale_count": min(
            item.scale_count for item in typed_diagnostics.values()
        ),
    }


def q_fluctuation(variances: Sequence[float], q_value: float, epsilon: float) -> float:
    """Return q-order fluctuation from positive variances.

    Example:
        `value = q_fluctuation([0.1, 0.2], 2.0, 1e-12)`
    """
    safe_values = [max(abs(value), epsilon) for value in variances]
    if q_value == 0.0:
        log_mean = sum(math.log(value) for value in safe_values) / len(safe_values)
        return math.exp(0.5 * log_mean)
    mean_power = sum(value ** (q_value / 2.0) for value in safe_values)
    return (mean_power / len(safe_values)) ** (1.0 / q_value)


def fluctuation_functions_from_variances(
    q_grid: Sequence[float],
    scale_variances: dict[int, tuple[float, ...]],
    epsilon: float,
) -> dict[str, tuple[tuple[int, float], ...]]:
    """Build q fluctuation functions from per-scale variances.

    Example:
        `functions = fluctuation_functions_from_variances(q_grid, variances, 1e-12)`
    """
    return {
        q_label(q_value): tuple(
            (scale, q_fluctuation(variances, q_value, epsilon))
            for scale, variances in scale_variances.items()
        )
        for q_value in q_grid
    }


def mean(values: Sequence[float]) -> float:
    """Return the arithmetic mean of a non-empty sequence.

    Example:
        `value = mean([1.0, 2.0])`
    """
    return sum(values) / len(values)


def population_variance(values: Sequence[float]) -> float:
    """Return population variance for a non-empty sequence.

    Example:
        `variance = population_variance([1.0, 2.0])`
    """
    center = mean(values)
    return sum((value - center) ** 2 for value in values) / len(values)


def _configured_or_default_scales(
    length: int,
    config: MFDFAConfig,
) -> tuple[int, ...]:
    if config.scales is not None:
        return tuple(sorted(set(config.scales)))
    return default_scale_grid(
        length,
        config.min_scale,
        config.max_scale,
        config.preferred_scale_count,
        config.detrending_order,
        config.min_segments_per_scale,
    )


def validate_method_config(config: MFDFAConfig) -> None:
    if config.detrending_order < 0:
        raise ValueError(
            f"Invalid detrending_order {config.detrending_order!r}; expected >= 0"
        )
    _positive_int(config.min_segments_per_scale, "min_segments_per_scale")
    _positive_int(config.min_scale_count, "min_scale_count")
    _positive_int(config.preferred_scale_count, "preferred_scale_count")
    if config.epsilon <= 0.0:
        raise ValueError(f"Invalid epsilon {config.epsilon!r}; expected positive")
    for q_value in config.q_grid:
        _finite_float(q_value, "q_grid")


def _validate_scale_count(
    scales: Sequence[int],
    config: MFDFAConfig,
    method: str,
) -> None:
    if len(scales) >= config.min_scale_count:
        return
    raise ValueError(
        f"Invalid {method} scales {scales!r}; "
        f"expected at least {config.min_scale_count}"
    )


def _validate_scale(scale: int, length: int, config: MFDFAConfig, method: str) -> None:
    if not isinstance(scale, int) or not 2 <= scale < length:
        raise ValueError(
            f"Invalid {method} scale {scale!r}; expected integer in [2, {length})"
        )
    segment_count = length // scale
    if segment_count >= config.min_segments_per_scale:
        return
    raise ValueError(
        f"Invalid {method} scale {scale!r}; expected at least "
        f"{config.min_segments_per_scale} segments, got {segment_count}"
    )


def _diagnostic_warnings(diagnostics: object) -> tuple[str, ...]:
    typed_diagnostics = _typed_diagnostics(diagnostics)
    warnings: list[str] = []
    for label, diagnostic in typed_diagnostics.items():
        warnings.extend(f"q={label}:{warning}" for warning in diagnostic.warnings)
    return tuple(warnings)


def _typed_spectrum(spectrum: object) -> MultifractalSpectrum:
    if isinstance(spectrum, MultifractalSpectrum):
        return spectrum
    raise ValueError(f"Invalid spectrum {spectrum!r}; expected MultifractalSpectrum")


def _typed_diagnostics(diagnostics: object) -> dict[str, ScalingDiagnostics]:
    if isinstance(diagnostics, dict):
        return {
            str(label): _typed_diagnostic(value)
            for label, value in diagnostics.items()
        }
    raise ValueError(f"Invalid diagnostics {diagnostics!r}; expected dict")


def _typed_diagnostic(value: object) -> ScalingDiagnostics:
    if isinstance(value, ScalingDiagnostics):
        return value
    raise ValueError(f"Invalid diagnostic {value!r}; expected ScalingDiagnostics")


def _finite_float(value: object, label: str) -> float:
    try:
        parsed = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(
            f"Invalid {label} value {value!r}; expected finite float"
        ) from exc
    if math.isfinite(parsed):
        return parsed
    raise ValueError(f"Invalid {label} value {value!r}; expected finite float")


def _positive_int(value: int, label: str) -> None:
    if isinstance(value, int) and value > 0:
        return
    raise ValueError(f"Invalid {label} {value!r}; expected positive integer")
