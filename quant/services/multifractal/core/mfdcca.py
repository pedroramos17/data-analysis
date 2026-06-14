"""Multifractal detrended cross-correlation analysis."""

from __future__ import annotations

import math
from collections.abc import Sequence

from quant.services.multifractal.core.detrending import detrended_residuals
from quant.services.multifractal.core.method_utils import (
    finite_series,
    mean,
    q_fluctuation,
    resolve_method_scales,
)
from quant.services.multifractal.core.scaling import build_scaling_diagnostic
from quant.services.multifractal.core.spectrum import q_label
from quant.services.multifractal.core.types import (
    MFDCCAResult,
    MFDFAConfig,
    ScalingDiagnostics,
)


def run_mfdcca(
    left_series: Sequence[float],
    right_series: Sequence[float],
    config: MFDFAConfig | None = None,
) -> MFDCCAResult:
    """Run MF-DCCA / MF-X-DFA over two aligned numeric series.

    Example:
        `result = run_mfdcca(asset_returns, index_returns, MFDFAConfig())`
    """
    active_config = config or MFDFAConfig()
    left, right = _aligned_series(left_series, right_series)
    scales = resolve_method_scales(len(left), active_config, "mfdcca")
    segment_bounds = {
        str(scale): _segment_bounds(
            len(left),
            scale,
            active_config.use_reverse_segments,
        )
        for scale in scales
    }
    covariances = _scale_covariances(left, right, segment_bounds, active_config)
    functions = _q_cross_fluctuations(covariances, active_config)
    diagnostics = _cross_diagnostics(functions, active_config)
    correlations = _scale_correlations(left, right, segment_bounds, active_config)
    return MFDCCAResult(
        "mfdcca",
        active_config,
        tuple(float(value) for value in active_config.q_grid),
        scales,
        functions,
        correlations,
        diagnostics,
        _joint_metrics(diagnostics, correlations),
        segment_bounds,
        _diagnostic_warnings(diagnostics),
    )


def _aligned_series(
    left_series: Sequence[float],
    right_series: Sequence[float],
) -> tuple[list[float], list[float]]:
    left = finite_series(left_series, "left_series")
    right = finite_series(right_series, "right_series")
    if len(left) == len(right):
        return left, right
    raise ValueError(
        f"Invalid paired series lengths {(len(left), len(right))!r}; "
        "expected equal-length aligned series"
    )


def _segment_bounds(
    length: int,
    scale: int,
    use_reverse_segments: bool,
) -> tuple[tuple[int, int], ...]:
    segment_count = length // scale
    forward = [
        (index * scale, (index + 1) * scale - 1)
        for index in range(segment_count)
    ]
    if not use_reverse_segments or length % scale == 0:
        return tuple(forward)
    backward = [
        (length - (index + 1) * scale, length - index * scale - 1)
        for index in range(segment_count)
    ]
    return tuple(forward + backward)


def _scale_covariances(
    left: Sequence[float],
    right: Sequence[float],
    segment_bounds: dict[str, tuple[tuple[int, int], ...]],
    config: MFDFAConfig,
) -> dict[int, tuple[float, ...]]:
    return {
        int(scale): tuple(
            _detrended_covariance(left[start : end + 1], right[start : end + 1], config)
            for start, end in bounds
        )
        for scale, bounds in segment_bounds.items()
    }


def _detrended_covariance(
    left: Sequence[float],
    right: Sequence[float],
    config: MFDFAConfig,
) -> float:
    left_residuals = detrended_residuals(left, config.detrending_order)
    right_residuals = detrended_residuals(right, config.detrending_order)
    products = [
        left * right
        for left, right in zip(left_residuals, right_residuals, strict=True)
    ]
    return mean(products)


def _q_cross_fluctuations(
    covariances: dict[int, tuple[float, ...]],
    config: MFDFAConfig,
) -> dict[str, tuple[tuple[int, float], ...]]:
    return {
        q_label(q_value): tuple(
            (scale, q_fluctuation(values, q_value, config.epsilon))
            for scale, values in covariances.items()
        )
        for q_value in config.q_grid
    }


def _cross_diagnostics(
    functions: dict[str, tuple[tuple[int, float], ...]],
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
        for label, points in functions.items()
    }


def _scale_correlations(
    left: Sequence[float],
    right: Sequence[float],
    segment_bounds: dict[str, tuple[tuple[int, int], ...]],
    config: MFDFAConfig,
) -> dict[str, float]:
    return {
        scale: _mean_scale_correlation(left, right, bounds, config)
        for scale, bounds in segment_bounds.items()
    }


def _mean_scale_correlation(
    left: Sequence[float],
    right: Sequence[float],
    bounds: Sequence[tuple[int, int]],
    config: MFDFAConfig,
) -> float:
    correlations = [
        _segment_correlation(left[start : end + 1], right[start : end + 1], config)
        for start, end in bounds
    ]
    return mean(correlations)


def _segment_correlation(
    left: Sequence[float],
    right: Sequence[float],
    config: MFDFAConfig,
) -> float:
    left_residuals = detrended_residuals(left, config.detrending_order)
    right_residuals = detrended_residuals(right, config.detrending_order)
    covariance = mean(
        [
            left * right
            for left, right in zip(left_residuals, right_residuals, strict=True)
        ]
    )
    denominator = _residual_std(left_residuals) * _residual_std(right_residuals)
    if denominator == 0.0:
        return 0.0
    return max(-1.0, min(1.0, covariance / denominator))


def _residual_std(values: Sequence[float]) -> float:
    center = mean(values)
    return math.sqrt(mean([(value - center) ** 2 for value in values]))


def _joint_metrics(
    diagnostics: dict[str, ScalingDiagnostics],
    correlations: dict[str, float],
) -> dict[str, float | int]:
    typed = {label: _diagnostic_slope(value) for label, value in diagnostics.items()}
    return {
        "joint_hurst_h2": typed.get("2", next(iter(typed.values()))),
        "cross_correlation_mean": mean(list(correlations.values())),
        "valid_scale_count": min(
            _diagnostic_scale_count(value) for value in diagnostics.values()
        ),
    }


def _diagnostic_warnings(
    diagnostics: dict[str, ScalingDiagnostics],
) -> tuple[str, ...]:
    warnings: list[str] = []
    for label, diagnostic in diagnostics.items():
        warnings.extend(
            f"q={label}:{warning}" for warning in _diagnostic_warning_values(diagnostic)
        )
    return tuple(warnings)


def _diagnostic_slope(value: object) -> float:
    if isinstance(value, ScalingDiagnostics):
        return value.slope
    raise ValueError(f"Invalid diagnostic {value!r}; expected ScalingDiagnostics")


def _diagnostic_scale_count(value: object) -> int:
    if isinstance(value, ScalingDiagnostics):
        return value.scale_count
    raise ValueError(f"Invalid diagnostic {value!r}; expected ScalingDiagnostics")


def _diagnostic_warning_values(value: object) -> tuple[str, ...]:
    if isinstance(value, ScalingDiagnostics):
        return value.warnings
    raise ValueError(f"Invalid diagnostic {value!r}; expected ScalingDiagnostics")
