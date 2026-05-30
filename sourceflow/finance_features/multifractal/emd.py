"""EMD/IMF feature interface with safe dependency handling."""

from __future__ import annotations

from sourceflow.config.feature_flags import require_feature

Number = float | int


def imf_energy_features(series: list[Number]) -> dict[str, object]:
    """Return IMF energy features when PyEMD is installed and enabled.

    Example:
        `features = imf_energy_features([1, 2, 3, 4])`
    """
    require_feature("FIN_MULTIFRACTAL_EMD")
    try:
        return _pyemd_features(series)
    except ImportError:
        return {
            "imf_energy_json": {},
            "quality_flags_json": {"missing_dependency": "PyEMD"},
        }


def _pyemd_features(series: list[Number]) -> dict[str, object]:
    from PyEMD import EMD

    imfs = EMD().emd([float(value) for value in series])
    energies = {f"imf_{index}": _energy(values) for index, values in enumerate(imfs)}
    return {"imf_energy_json": energies, "quality_flags_json": {}}


def _energy(values: object) -> float:
    return float(sum(float(value) ** 2 for value in values))
