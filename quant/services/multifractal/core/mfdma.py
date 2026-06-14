"""Multifractal Detrended Moving Average analysis."""

from __future__ import annotations

from collections.abc import Sequence

from quant.services.multifractal.core.method_utils import (
    build_method_result,
    centered_profile,
    finite_series,
    fluctuation_functions_from_variances,
    mean,
    population_variance,
    resolve_method_scales,
)
from quant.services.multifractal.core.types import (
    MFDFAConfig,
    MultifractalMethodResult,
)

MOVING_AVERAGE_MODES = ("backward", "centered", "forward")


def run_mfdma(
    series: Sequence[float],
    config: MFDFAConfig | None = None,
    moving_average_mode: str = "backward",
) -> MultifractalMethodResult:
    """Run MF-DMA with backward, centered, or forward moving averages.

    Example:
        `result = run_mfdma(returns, MFDFAConfig(), "centered")`
    """
    active_config = config or MFDFAConfig()
    _validate_moving_average_mode(moving_average_mode)
    values = finite_series(series)
    scales = resolve_method_scales(len(values), active_config, "mfdma")
    profile = centered_profile(values)
    scale_variances = {
        scale: _scale_residual_variances(profile, scale, moving_average_mode)
        for scale in scales
    }
    functions = fluctuation_functions_from_variances(
        active_config.q_grid,
        scale_variances,
        active_config.epsilon,
    )
    return build_method_result(
        "mfdma",
        active_config,
        scales,
        functions,
        {"moving_average_mode": moving_average_mode},
    )


def _scale_residual_variances(
    profile: Sequence[float],
    scale: int,
    mode: str,
) -> tuple[float, ...]:
    residuals = _moving_average_residuals(profile, scale, mode)
    return tuple(
        population_variance(residuals[start : start + scale])
        for start in range(0, len(residuals) - scale + 1, scale)
    )


def _moving_average_residuals(
    profile: Sequence[float],
    scale: int,
    mode: str,
) -> list[float]:
    if mode == "backward":
        return _backward_residuals(profile, scale)
    if mode == "centered":
        return _centered_residuals(profile, scale)
    return _forward_residuals(profile, scale)


def _backward_residuals(profile: Sequence[float], scale: int) -> list[float]:
    return [
        profile[index] - mean(profile[index - scale + 1 : index + 1])
        for index in range(scale - 1, len(profile))
    ]


def _centered_residuals(profile: Sequence[float], scale: int) -> list[float]:
    left = scale // 2
    right = scale - left
    return [
        profile[index] - mean(profile[index - left : index + right])
        for index in range(left, len(profile) - right + 1)
    ]


def _forward_residuals(profile: Sequence[float], scale: int) -> list[float]:
    return [
        profile[index] - mean(profile[index : index + scale])
        for index in range(0, len(profile) - scale + 1)
    ]


def _validate_moving_average_mode(mode: str) -> None:
    if mode in MOVING_AVERAGE_MODES:
        return
    raise ValueError(
        f"Invalid moving_average_mode {mode!r}; "
        f"expected one of {MOVING_AVERAGE_MODES}"
    )
