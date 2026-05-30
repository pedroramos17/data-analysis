"""Joint multifractal and cross-correlation feature baselines."""

from __future__ import annotations

from sourceflow.finance_features.multifractal.mfdfa import generalized_hurst_exponent

Number = float | int


def mf_dcca_like(series_a: list[Number], series_b: list[Number]) -> dict[str, float]:
    """Return a lightweight MF-DCCA-like baseline.

    Example:
        `features = mf_dcca_like([1, 2], [2, 3])`
    """
    paired = [float(a) * float(b) for a, b in zip(series_a, series_b, strict=False)]
    return {
        "joint_hurst": generalized_hurst_exponent(paired),
        "overlap": float(len(paired)),
    }


def multifractal_similarity(
    hurst_a: dict[str, float],
    hurst_b: dict[str, float],
) -> float:
    """Return a bounded similarity score from shared Hurst keys.

    Example:
        `score = multifractal_similarity({"2": .5}, {"2": .6})`
    """
    keys = sorted(set(hurst_a) & set(hurst_b))
    if not keys:
        return 0.0
    distance = sum(abs(hurst_a[key] - hurst_b[key]) for key in keys) / len(keys)
    return max(0.0, 1.0 - distance)
