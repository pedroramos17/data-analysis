"""Multifractal spectrum construction for Quant4 MF-DFA."""

from __future__ import annotations

from collections.abc import Sequence

from quant4.services.multifractal.core.types import MultifractalSpectrum


def q_label(value: float) -> str:
    """Return a stable JSON-friendly q label.

    Example:
        `label = q_label(2.0)`
    """
    return str(int(value)) if float(value).is_integer() else str(value)


def build_multifractal_spectrum(
    q_grid: Sequence[float],
    hq: dict[str, float],
) -> MultifractalSpectrum:
    """Build tau(q), alpha, f(alpha), and summary metrics.

    Example:
        `spectrum = build_multifractal_spectrum((-2.0, 0.0, 2.0), hq)`
    """
    sorted_q = tuple(sorted(float(value) for value in q_grid))
    tau = {q_label(q): q * hq[q_label(q)] - 1.0 for q in sorted_q}
    alpha = _tau_derivative(sorted_q, tau)
    f_alpha = tuple(
        q * alpha[index] - tau[q_label(q)] for index, q in enumerate(sorted_q)
    )
    peak_alpha = alpha[_peak_index(f_alpha)]
    width = max(alpha) - min(alpha)
    return MultifractalSpectrum(
        sorted_q,
        hq,
        tau,
        alpha,
        f_alpha,
        _hurst_h2(sorted_q, hq),
        width,
        peak_alpha,
        width,
        _spectrum_asymmetry(alpha, peak_alpha),
        max(hq.values()) - min(hq.values()),
        _tau_nonlinearity(sorted_q, tau),
    )


def _tau_derivative(
    q_grid: Sequence[float],
    tau: dict[str, float],
) -> tuple[float, ...]:
    if len(q_grid) == 1:
        return (0.0,)
    return tuple(_tau_slope_at(q_grid, tau, index) for index in range(len(q_grid)))


def _tau_slope_at(q_grid: Sequence[float], tau: dict[str, float], index: int) -> float:
    if index == 0:
        return _tau_pair_slope(q_grid[0], q_grid[1], tau)
    if index == len(q_grid) - 1:
        return _tau_pair_slope(q_grid[-2], q_grid[-1], tau)
    return _tau_pair_slope(q_grid[index - 1], q_grid[index + 1], tau)


def _tau_pair_slope(left_q: float, right_q: float, tau: dict[str, float]) -> float:
    return (tau[q_label(right_q)] - tau[q_label(left_q)]) / (right_q - left_q)


def _peak_index(values: Sequence[float]) -> int:
    return max(range(len(values)), key=lambda index: values[index])


def _hurst_h2(q_grid: Sequence[float], hq: dict[str, float]) -> float:
    if "2" in hq:
        return hq["2"]
    nearest = min(q_grid, key=lambda q: abs(q - 2.0))
    return hq[q_label(nearest)]


def _spectrum_asymmetry(alpha: Sequence[float], peak_alpha: float) -> float:
    width = max(alpha) - min(alpha)
    if width == 0.0:
        return 0.0
    left_width = peak_alpha - min(alpha)
    right_width = max(alpha) - peak_alpha
    return (right_width - left_width) / width


def _tau_nonlinearity(q_grid: Sequence[float], tau: dict[str, float]) -> float:
    if len(q_grid) <= 2:
        return 0.0
    left_q = q_grid[0]
    right_q = q_grid[-1]
    slope = _tau_pair_slope(left_q, right_q, tau)
    intercept = tau[q_label(left_q)] - slope * left_q
    errors = [abs(tau[q_label(q)] - (slope * q + intercept)) for q in q_grid]
    return sum(errors) / len(errors)
