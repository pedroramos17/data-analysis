"""Production MF-DFA implementation for Quant4 multifractal analysis."""

from __future__ import annotations

import math
from collections.abc import Sequence

from quant4.services.multifractal.core.detrending import detrended_variance
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
    MFDFAResult,
    MultifractalSpectrum,
    ScalingDiagnostics,
    SummaryValue,
)

MIN_OBSERVATIONS = 16


def run_mfdfa(
    series: Sequence[float],
    config: MFDFAConfig | None = None,
) -> MFDFAResult:
    """Run MF-DFA on a one-dimensional finite numeric series.

    Example:
        `result = run_mfdfa([0.01, -0.02, 0.03, 0.01] * 16)`
    """
    active_config = config or MFDFAConfig()
    _validate_config(active_config)
    values = _coerce_series(series)
    _validate_series_length(values, active_config)
    scales = _resolve_scales(len(values), active_config)
    fluctuation_functions = _fluctuation_functions(values, scales, active_config)
    diagnostics = _fit_all_scaling_exponents(fluctuation_functions, active_config)
    hq = {label: diagnostic.slope for label, diagnostic in diagnostics.items()}
    spectrum = build_multifractal_spectrum(active_config.q_grid, hq)
    warnings = _collect_warnings(diagnostics)
    return MFDFAResult(
        active_config,
        tuple(float(value) for value in active_config.q_grid),
        scales,
        fluctuation_functions,
        spectrum,
        diagnostics,
        {label: item.r_squared for label, item in diagnostics.items()},
        min(item.scale_count for item in diagnostics.values()),
        _summary(spectrum, diagnostics),
        warnings,
    )


def _fluctuation_functions(
    values: Sequence[float],
    scales: Sequence[int],
    config: MFDFAConfig,
) -> dict[str, tuple[tuple[int, float], ...]]:
    profile = _profile(values)
    variances_by_scale = {
        scale: _segment_variances(profile, scale, config) for scale in scales
    }
    return {
        q_label(q): tuple(
            (scale, _fluctuation_at_q(variances_by_scale[scale], q, config.epsilon))
            for scale in scales
        )
        for q in config.q_grid
    }


def _fit_all_scaling_exponents(
    fluctuation_functions: dict[str, tuple[tuple[int, float], ...]],
    config: MFDFAConfig,
) -> dict[str, ScalingDiagnostics]:
    return {
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


def _profile(values: Sequence[float]) -> list[float]:
    center = sum(values) / len(values)
    cumulative = 0.0
    profile: list[float] = []
    for value in values:
        cumulative += value - center
        profile.append(cumulative)
    return profile


def _segment_variances(
    profile: Sequence[float],
    scale: int,
    config: MFDFAConfig,
) -> tuple[float, ...]:
    starts = _segment_starts(len(profile), scale, config.use_reverse_segments)
    return tuple(
        detrended_variance(profile[start : start + scale], config.detrending_order)
        for start in starts
    )


def _segment_starts(
    length: int,
    scale: int,
    use_reverse_segments: bool,
) -> tuple[int, ...]:
    segment_count = length // scale
    forward = [index * scale for index in range(segment_count)]
    if not use_reverse_segments or length % scale == 0:
        return tuple(forward)
    backward = [length - (index + 1) * scale for index in range(segment_count)]
    return tuple(forward + backward)


def _fluctuation_at_q(
    variances: Sequence[float],
    q: float,
    epsilon: float,
) -> float:
    safe_variances = [max(value, epsilon) for value in variances]
    if q == 0.0:
        log_mean = sum(math.log(value) for value in safe_variances)
        return math.exp(0.5 * log_mean / len(safe_variances))
    mean_power = (
        sum(value ** (q / 2.0) for value in safe_variances) / len(safe_variances)
    )
    return mean_power ** (1.0 / q)


def _resolve_scales(length: int, config: MFDFAConfig) -> tuple[int, ...]:
    if config.scales is not None:
        scales = tuple(sorted(set(config.scales)))
    else:
        scales = default_scale_grid(
            length,
            config.min_scale,
            config.max_scale,
            config.preferred_scale_count,
            config.detrending_order,
            config.min_segments_per_scale,
        )
    _validate_scales(scales, length, config)
    return scales


def _validate_scales(scales: Sequence[int], length: int, config: MFDFAConfig) -> None:
    if len(scales) < config.min_scale_count:
        raise ValueError(
            f"Invalid scales {scales!r}; expected at least {config.min_scale_count}"
        )
    for scale in scales:
        _validate_scale(scale, length, config)


def _validate_scale(scale: int, length: int, config: MFDFAConfig) -> None:
    min_scale = config.detrending_order + 3
    if not isinstance(scale, int) or not min_scale <= scale < length:
        raise ValueError(
            f"Invalid scale {scale!r}; expected integer in [{min_scale}, {length})"
        )
    segment_count = length // scale
    if segment_count >= config.min_segments_per_scale:
        return
    raise ValueError(
        f"Invalid scale {scale!r}; expected at least "
        f"{config.min_segments_per_scale} segments, got {segment_count}"
    )


def _validate_config(config: MFDFAConfig) -> None:
    if config.detrending_order < 0:
        raise ValueError(
            f"Invalid detrending_order {config.detrending_order!r}; expected >= 0"
        )
    _validate_q_grid(config.q_grid)
    _validate_positive_config_int(
        config.min_segments_per_scale,
        "min_segments_per_scale",
    )
    _validate_positive_config_int(config.min_scale_count, "min_scale_count")
    _validate_positive_config_int(config.preferred_scale_count, "preferred_scale_count")
    if config.epsilon <= 0.0:
        raise ValueError(f"Invalid epsilon {config.epsilon!r}; expected positive float")


def _validate_positive_config_int(value: int, label: str) -> None:
    if isinstance(value, int) and value > 0:
        return
    raise ValueError(f"Invalid {label} {value!r}; expected positive integer")


def _validate_q_grid(q_grid: Sequence[float]) -> None:
    if not q_grid:
        raise ValueError(f"Invalid q_grid {q_grid!r}; expected non-empty q grid")
    for value in q_grid:
        if math.isfinite(float(value)):
            continue
        raise ValueError(f"Invalid q_grid value {value!r}; expected finite float")


def _coerce_series(series: Sequence[float]) -> list[float]:
    if not series:
        raise ValueError(f"Invalid series {series!r}; expected finite numeric series")
    values = [_finite_float(value) for value in series]
    return values


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


def _validate_series_length(values: Sequence[float], config: MFDFAConfig) -> None:
    minimum = max(
        MIN_OBSERVATIONS,
        (config.detrending_order + 3) * config.min_scale_count,
    )
    if len(values) >= minimum:
        return
    raise ValueError(
        f"Invalid series length {len(values)!r}; expected at least {minimum}"
    )


def _collect_warnings(diagnostics: dict[str, ScalingDiagnostics]) -> tuple[str, ...]:
    warnings: list[str] = []
    for label, diagnostic in diagnostics.items():
        warnings.extend(f"q={label}:{warning}" for warning in diagnostic.warnings)
    return tuple(warnings)


def _summary(
    spectrum: MultifractalSpectrum,
    diagnostics: dict[str, ScalingDiagnostics],
) -> dict[str, SummaryValue]:
    mean_r2 = sum(item.r_squared for item in diagnostics.values()) / len(diagnostics)
    return {
        "hurst_h2": spectrum.hurst_h2,
        "delta_alpha": spectrum.delta_alpha,
        "alpha_peak": spectrum.alpha_peak,
        "spectrum_width": spectrum.spectrum_width,
        "spectrum_asymmetry": spectrum.spectrum_asymmetry,
        "hq_range": spectrum.hq_range,
        "tau_nonlinearity": spectrum.tau_nonlinearity,
        "scaling_quality_mean_r2": mean_r2,
        "valid_scale_count": min(item.scale_count for item in diagnostics.values()),
    }
