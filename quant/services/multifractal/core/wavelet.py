"""Wavelet diagnostics interface for Quant multifractal research."""

from __future__ import annotations

import importlib
import math
from collections.abc import Sequence
from dataclasses import dataclass

from quant.services.multifractal.core.method_utils import finite_series, mean
from quant.services.multifractal.core.spectrum import q_label


@dataclass(frozen=True, slots=True)
class WaveletDiagnosticResult:
    """Scale-energy diagnostics from optional CWT or local fallback.

    Example:
        `result = run_wavelet_diagnostics(returns, scales=(2, 4, 8))`
    """

    method: str
    scales: tuple[int, ...]
    energy_by_scale: dict[str, float]
    dominant_scale: int
    limitations: tuple[str, ...]
    warnings: tuple[str, ...]

    def to_json_dict(self) -> dict[str, object]:
        """Return a JSON-serializable wavelet diagnostic payload.

        Example:
            `payload = result.to_json_dict()`
        """
        return {
            "method": self.method,
            "scales": list(self.scales),
            "energy_by_scale": self.energy_by_scale,
            "dominant_scale": self.dominant_scale,
            "limitations": list(self.limitations),
            "warnings": list(self.warnings),
        }


def run_wavelet_diagnostics(
    series: Sequence[float],
    scales: Sequence[int] = (2, 4, 8, 16),
    prefer_pywavelets: bool = True,
) -> WaveletDiagnosticResult:
    """Run minimal CWT-style energy diagnostics with a local fallback.

    Example:
        `result = run_wavelet_diagnostics(returns, scales=(2, 4, 8))`
    """
    values = finite_series(series)
    scale_values = _validate_scales(scales, len(values))
    if prefer_pywavelets:
        pywavelets_result = _try_pywavelets(values, scale_values)
        if pywavelets_result is not None:
            return pywavelets_result
    return _ricker_fallback_result(values, scale_values)


def _try_pywavelets(
    values: Sequence[float],
    scales: tuple[int, ...],
) -> WaveletDiagnosticResult | None:
    try:
        pywt = importlib.import_module("pywt")
        coefficients, _frequencies = pywt.cwt(values, scales, "mexh")
    except (ImportError, AttributeError, ValueError):
        return None
    energy = {
        q_label(float(scale)): mean([float(value) ** 2 for value in row])
        for scale, row in zip(scales, coefficients, strict=True)
    }
    return _result("pywavelets_cwt", scales, energy, tuple())


def _ricker_fallback_result(
    values: Sequence[float],
    scales: tuple[int, ...],
) -> WaveletDiagnosticResult:
    energy = {
        q_label(float(scale)): mean(
            [
                coefficient * coefficient
                for coefficient in _ricker_coefficients(values, scale)
            ]
        )
        for scale in scales
    }
    return _result("ricker_fallback", scales, energy, ("pywavelets_missing",))


def _ricker_coefficients(values: Sequence[float], scale: int) -> list[float]:
    radius = max(2, scale * 4)
    return [
        _ricker_at_center(values, center, scale, radius)
        for center in range(len(values))
    ]


def _ricker_at_center(
    values: Sequence[float],
    center: int,
    scale: int,
    radius: int,
) -> float:
    total = 0.0
    weight_total = 0.0
    for offset in range(-radius, radius + 1):
        index = center + offset
        if 0 <= index < len(values):
            weight = _ricker_weight(offset / float(scale))
            total += values[index] * weight
            weight_total += abs(weight)
    if weight_total == 0.0:
        return 0.0
    return total / weight_total


def _ricker_weight(position: float) -> float:
    return (1.0 - position * position) * math.exp(-(position * position) / 2.0)


def _result(
    method: str,
    scales: tuple[int, ...],
    energy: dict[str, float],
    warnings: tuple[str, ...],
) -> WaveletDiagnosticResult:
    dominant = max(scales, key=lambda scale: energy[q_label(float(scale))])
    return WaveletDiagnosticResult(
        method,
        scales,
        energy,
        dominant,
        ("not_wavelet_leader_spectrum", "diagnostic_energy_only"),
        warnings,
    )


def _validate_scales(scales: Sequence[int], length: int) -> tuple[int, ...]:
    if not scales:
        raise ValueError(f"Invalid wavelet scales {scales!r}; expected non-empty")
    values = tuple(int(scale) for scale in scales)
    for scale in values:
        if 1 < scale < length:
            continue
        raise ValueError(
            f"Invalid wavelet scale {scale!r}; expected integer in [2, {length})"
        )
    return values
