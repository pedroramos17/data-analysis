"""Shared helpers for Quant4 multifractal management commands."""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence


def parse_float_series(raw_value: str) -> list[float]:
    """Parse a comma-separated finite numeric series.

    Example:
        `values = parse_float_series("0.1,-0.2")`
    """
    values = [float(item.strip()) for item in raw_value.split(",") if item.strip()]
    if values:
        return values
    raise ValueError(f"Invalid series {raw_value!r}; expected comma-separated floats")


def parse_symbols(raw_value: str) -> list[str]:
    """Parse a comma-separated symbol list."""
    symbols = [item.strip().upper() for item in raw_value.split(",") if item.strip()]
    if symbols:
        return symbols
    raise ValueError(f"Invalid symbols {raw_value!r}; expected comma-separated symbols")


def diagonal_covariance(variances: Sequence[float]) -> list[list[float]]:
    """Return a diagonal covariance matrix from variances."""
    return [
        [
            float(value) if row_index == column_index else 0.0
            for column_index, value in enumerate(variances)
        ]
        for row_index in range(len(variances))
    ]


def regime_feature_rows(series: Sequence[float]) -> list[dict[str, float]]:
    """Build simple rolling feature rows for CLI regime smoke runs."""
    return [
        {
            "hurst_h2": 0.5,
            "delta_alpha": abs(float(value)),
            "spectrum_asymmetry": float(value),
            "tau_nonlinearity": abs(float(value)),
            "realized_volatility": abs(float(value)),
            "drawdown": min(0.0, float(value)),
        }
        for value in series
    ]


def json_text(payload: Mapping[str, object]) -> str:
    """Serialize payload as stable, user-facing JSON."""
    return json.dumps(payload, sort_keys=True)


def default_cli_series() -> list[float]:
    """Return a deterministic fallback series for smoke commands."""
    return [0.01, -0.02, 0.015, -0.005] * 16
