"""Build persisted multifractal feature-set payloads."""

from __future__ import annotations

from sourceflow.config.feature_flags import require_feature
from sourceflow.finance_features.multifractal.mfdfa import mfdfa
from sourceflow.finance_features.multifractal.roughness import (
    intermittency_proxy,
    path_roughness,
    spectrum_width,
)
from sourceflow.finance_features.multifractal.wavelet import wavelet_energy_features

Number = float | int


def build_multifractal_feature_set(prices: list[Number]) -> dict[str, object]:
    """Build a lightweight multifractal feature set for one price window.

    Example:
        `features = build_multifractal_feature_set([100, 101, 102])`
    """
    require_feature("FIN_MULTIFRACTAL_CORE")
    baseline = mfdfa(prices)
    hurst = baseline["hurst_json"]
    alpha = baseline["alpha_json"]
    return baseline | {
        "method": "mfdfa_wavelet",
        "spectrum_width": spectrum_width(alpha),
        "roughness": path_roughness(prices),
        "intermittency": intermittency_proxy(hurst),
        "wavelet_energy_json": wavelet_energy_features(prices),
        "quality_flags_json": {},
    }
