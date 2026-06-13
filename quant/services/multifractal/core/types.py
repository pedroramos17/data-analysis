"""Typed result objects for Quant multifractal core algorithms."""

from __future__ import annotations

from dataclasses import dataclass, field

SummaryValue = float | int | str | bool
MetadataValue = SummaryValue | None


def default_mfdfa_q_grid() -> tuple[float, ...]:
    """Return the default MF-DFA q grid.

    Example:
        `q_grid = default_mfdfa_q_grid()`
    """
    return tuple(float(value) for value in range(-5, 6))


@dataclass(frozen=True, slots=True)
class MFDFAConfig:
    """Configuration for local-first MF-DFA estimation.

    Example:
        `config = MFDFAConfig(q_grid=(-2.0, 0.0, 2.0), scales=(8, 16, 32))`
    """

    q_grid: tuple[float, ...] = field(default_factory=default_mfdfa_q_grid)
    scales: tuple[int, ...] | None = None
    detrending_order: int = 1
    min_scale: int | None = None
    max_scale: int | None = None
    use_reverse_segments: bool = True
    robust_regression: bool = False
    min_segments_per_scale: int = 4
    min_scale_count: int = 3
    preferred_scale_count: int = 12
    epsilon: float = 1e-12


@dataclass(frozen=True, slots=True)
class ScalingDiagnostics:
    """Diagnostics for one q-specific log-log scaling fit.

    Example:
        `diagnostic = result.diagnostics_by_q["2"]`
    """

    q: float
    slope: float
    intercept: float
    r_squared: float
    scale_count: int
    scale_range: tuple[int, int]
    used_scales: tuple[int, ...]
    warnings: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class MultifractalSpectrum:
    """Legendre-spectrum summary derived from generalized Hurst exponents.

    Example:
        `width = result.spectrum.spectrum_width`
    """

    q_grid: tuple[float, ...]
    hq: dict[str, float]
    tau: dict[str, float]
    alpha: tuple[float, ...]
    f_alpha: tuple[float, ...]
    hurst_h2: float
    delta_alpha: float
    alpha_peak: float
    spectrum_width: float
    spectrum_asymmetry: float
    hq_range: float
    tau_nonlinearity: float


@dataclass(frozen=True, slots=True)
class MFDFAResult:
    """Complete MF-DFA output with diagnostics and fluctuation functions.

    Example:
        `result = run_mfdfa(returns, MFDFAConfig())`
    """

    config: MFDFAConfig
    q_grid: tuple[float, ...]
    scales: tuple[int, ...]
    fluctuation_functions: dict[str, tuple[tuple[int, float], ...]]
    spectrum: MultifractalSpectrum
    diagnostics_by_q: dict[str, ScalingDiagnostics]
    scaling_r2_by_q: dict[str, float]
    valid_scale_count: int
    summary: dict[str, SummaryValue]
    warnings: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class MultifractalMethodResult:
    """Common result object for additional multifractal methods.

    Example:
        `result = run_mfdma(returns, MFDFAConfig())`
    """

    method: str
    config: MFDFAConfig
    q_grid: tuple[float, ...]
    scales: tuple[int, ...]
    fluctuation_functions: dict[str, tuple[tuple[int, float], ...]]
    spectrum: MultifractalSpectrum
    diagnostics_by_q: dict[str, ScalingDiagnostics]
    scaling_r2_by_q: dict[str, float]
    valid_scale_count: int
    summary: dict[str, SummaryValue]
    warnings: tuple[str, ...]
    metadata: dict[str, MetadataValue]


@dataclass(frozen=True, slots=True)
class MFDCCAResult:
    """Joint multifractal detrended cross-correlation output.

    Example:
        `result = run_mfdcca(left_returns, right_returns, MFDFAConfig())`
    """

    method: str
    config: MFDFAConfig
    q_grid: tuple[float, ...]
    scales: tuple[int, ...]
    q_cross_fluctuations: dict[str, tuple[tuple[int, float], ...]]
    scale_correlations: dict[str, float]
    diagnostics_by_q: dict[str, ScalingDiagnostics]
    joint_metrics: dict[str, SummaryValue]
    segment_bounds_by_scale: dict[str, tuple[tuple[int, int], ...]]
    warnings: tuple[str, ...]
