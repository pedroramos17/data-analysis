"""Factor risk model helpers."""

from __future__ import annotations

from collections.abc import Sequence

from quant.services.risk.covariance import pca_risk_model


def build_factor_risk_model(series: Sequence[Sequence[float]]) -> dict[str, object]:
    """Return a local PCA-style factor risk proxy.

    Example:
        `build_factor_risk_model([[0.01, -0.02]])`
    """
    model = pca_risk_model(series)
    model["claim_scope"] = "risk_decomposition_only"
    return model
