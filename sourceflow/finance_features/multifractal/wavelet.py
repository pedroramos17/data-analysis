"""Wavelet energy features with a Haar fallback."""

from __future__ import annotations

from sourceflow.config.feature_flags import require_feature

Number = float | int


def wavelet_energy_features(series: list[Number], levels: int = 3) -> dict[str, float]:
    """Return wavelet energy features using pywt or a Haar fallback.

    Example:
        `features = wavelet_energy_features([1, 2, 3, 4])`
    """
    require_feature("FIN_MULTIFRACTAL_WAVELET")
    try:
        return _pywt_energy(series, levels)
    except ImportError:
        return _haar_energy([float(value) for value in series], levels)


def wtmm_features(series: list[Number]) -> dict[str, object]:
    """Reserve a WTMM interface without enabling unvalidated behavior.

    Example:
        `wtmm_features([1, 2, 3])`
    """
    require_feature("FIN_MULTIFRACTAL_WAVELET")
    raise NotImplementedError(
        "WTMM features are not implemented; expected validated method"
    )


def wavelet_leader_features(series: list[Number]) -> dict[str, object]:
    """Reserve a wavelet-leader interface for documented future work.

    Example:
        `wavelet_leader_features([1, 2, 3])`
    """
    require_feature("FIN_MULTIFRACTAL_WAVELET")
    raise NotImplementedError(
        "Wavelet leader features are not implemented; expected validated method"
    )


def _pywt_energy(series: list[Number], levels: int) -> dict[str, float]:
    import pywt

    coeffs = pywt.wavedec([float(value) for value in series], "haar", level=levels)
    return {
        f"pywt_level_{index}": _energy(values) for index, values in enumerate(coeffs)
    }


def _haar_energy(values: list[float], levels: int) -> dict[str, float]:
    energies: dict[str, float] = {}
    current = values
    for level in range(1, max(levels, 1) + 1):
        current, details = _haar_step(current)
        energies[f"haar_level_{level}"] = _energy(details)
        if len(current) < 2:
            break
    return energies


def _haar_step(values: list[float]) -> tuple[list[float], list[float]]:
    pairs = list(zip(values[0::2], values[1::2], strict=False))
    smooth = [(left + right) / 2.0 for left, right in pairs]
    detail = [(left - right) / 2.0 for left, right in pairs]
    return smooth or values, detail


def _energy(values: object) -> float:
    return float(sum(float(value) ** 2 for value in values))
