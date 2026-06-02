"""Multifractal feature engineering for Quant4 research workflows."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Sequence
from dataclasses import asdict, is_dataclass

from quant4.services.multifractal.core.diagnostics import run_multifractal_diagnostics
from quant4.services.multifractal.core.mfdcca import run_mfdcca
from quant4.services.multifractal.core.mfdfa import run_mfdfa
from quant4.services.multifractal.core.types import MFDFAConfig
from quant4.services.multifractal.defaults import (
    DEFAULT_DIAGNOSTIC_SEED,
    DIAGNOSTIC_BOOTSTRAP_COUNT,
    DIAGNOSTIC_FINITE_SIZE_SIMULATIONS,
)

FeatureValue = str | int | float | bool | dict[str, float] | dict[str, object]


def compute_multifractal_feature_row(
    symbol: str,
    series: Sequence[float],
    config: MFDFAConfig,
    window_id: str,
) -> dict[str, FeatureValue]:
    """Compute core MF-DFA features for one asset window.

    Example:
        `row = compute_multifractal_feature_row("SPY", returns, config, "w0")`
    """
    result = run_mfdfa(series, config)
    diagnostics = run_multifractal_diagnostics(
        series,
        config,
        seed=DEFAULT_DIAGNOSTIC_SEED,
        bootstrap_count=DIAGNOSTIC_BOOTSTRAP_COUNT,
        finite_size_simulations=DIAGNOSTIC_FINITE_SIZE_SIMULATIONS,
    )
    return {
        "symbol": symbol,
        "window_id": window_id,
        "hurst_h2": result.spectrum.hurst_h2,
        "generalized_hurst_hq": result.spectrum.hq,
        "delta_alpha": result.spectrum.delta_alpha,
        "alpha_min": min(result.spectrum.alpha),
        "alpha_max": max(result.spectrum.alpha),
        "alpha_peak": result.spectrum.alpha_peak,
        "spectrum_asymmetry": result.spectrum.spectrum_asymmetry,
        "tau_nonlinearity": result.spectrum.tau_nonlinearity,
        "intermittency_proxy": result.spectrum.hq_range,
        "scaling_quality_mean_r2": _mean_r2(result.scaling_r2_by_q),
        "finite_size_warning": diagnostics.finite_size.is_short_sample,
        "shuffle_delta_alpha_ratio": diagnostics.comparisons["shuffled"].ratio_metrics[
            "delta_alpha"
        ],
        "surrogate_delta_alpha_ratio": diagnostics.comparisons[
            "surrogate_phase"
        ].ratio_metrics["delta_alpha"],
        "extreme_sensitivity_score": diagnostics.extreme_value.sensitivity_score,
        "config_hash": config_hash(config),
    }


def compute_rolling_multifractal_features(
    symbol: str,
    series: Sequence[float],
    window_size: int,
    step: int,
    config: MFDFAConfig,
) -> list[dict[str, FeatureValue]]:
    """Compute no-lookahead rolling multifractal features.

    Example:
        `rows = compute_rolling_multifractal_features("SPY", returns, 128, 32, config)`
    """
    _positive_int(window_size, "window_size")
    _positive_int(step, "step")
    values = list(series)
    rows: list[dict[str, FeatureValue]] = []
    for start in range(0, len(values) - window_size + 1, step):
        end = start + window_size - 1
        row = compute_multifractal_feature_row(
            symbol,
            values[start : end + 1],
            config,
            f"{symbol}_{start}_{end}",
        )
        row["window_start"] = start
        row["window_end"] = end
        rows.append(row)
    return rows


def compute_cross_multifractal_features(
    asset_symbol: str,
    benchmark_symbol: str,
    asset_series: Sequence[float],
    benchmark_series: Sequence[float],
    config: MFDFAConfig,
) -> dict[str, FeatureValue]:
    """Compute MF-DCCA cross features for aligned asset/benchmark windows.

    Example:
        `row = compute_cross_multifractal_features("SPY", "SPX", a, b, config)`
    """
    result = run_mfdcca(asset_series, benchmark_series, config)
    return {
        "symbol": asset_symbol,
        "benchmark_symbol": benchmark_symbol,
        "mf_dcca_corr_asset_index": result.joint_metrics["cross_correlation_mean"],
        "mf_dcca_joint_hurst_h2": result.joint_metrics["joint_hurst_h2"],
        "scale_specific_cross_corr": result.scale_correlations,
        "config_hash": config_hash(config),
    }


def config_hash(config: MFDFAConfig) -> str:
    """Return a deterministic hash for feature reproducibility.

    Example:
        `digest = config_hash(MFDFAConfig())`
    """
    payload = _jsonable_config(config)
    raw = json.dumps(payload, sort_keys=True, default=str)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:24]


def _jsonable_config(config: MFDFAConfig) -> dict[str, object]:
    if is_dataclass(config):
        return asdict(config)
    raise ValueError(f"Invalid config {config!r}; expected MFDFAConfig")


def _mean_r2(values: dict[str, float]) -> float:
    return sum(values.values()) / len(values)


def _positive_int(value: int, label: str) -> None:
    if isinstance(value, int) and value > 0:
        return
    raise ValueError(f"Invalid {label} {value!r}; expected positive integer")
