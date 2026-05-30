"""Experimental HM-style range-restricted correlation correction."""

from __future__ import annotations

from math import atanh, sqrt, tanh

from sourceflow.config.feature_flags import require_feature


def hm_corrected_corr(
    r_obs: float,
    sx: float,
    sy: float,
    sx_total: float,
    sy_total: float,
    epsilon: float = 1e-12,
) -> float:
    """Return a bounded experimental correction for restricted correlations.

    Example:
        `hm_corrected_corr(0.4, 1, 1, 2, 2)`
    """
    require_feature("FIN_STATS_HM_CORRELATION")
    z_value = atanh(_bounded_corr(r_obs, epsilon))
    multiplier = sqrt(
        _safe_ratio(sx_total, sx, epsilon) * _safe_ratio(sy_total, sy, epsilon)
    )
    return max(-1.0, min(1.0, tanh(z_value * multiplier)))


def _bounded_corr(value: float, epsilon: float) -> float:
    return max(-1.0 + epsilon, min(1.0 - epsilon, float(value)))


def _safe_ratio(total: float, sample: float, epsilon: float) -> float:
    return max(float(total), epsilon) / max(float(sample), epsilon)
