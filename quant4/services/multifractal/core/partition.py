"""Partition-function multifractal baseline for positive measures."""

from __future__ import annotations

import math
from collections.abc import Sequence

from quant4.services.multifractal.core.method_utils import (
    build_method_result,
    positive_measure,
    resolve_method_scales,
)
from quant4.services.multifractal.core.spectrum import q_label
from quant4.services.multifractal.core.types import (
    MFDFAConfig,
    MultifractalMethodResult,
)


def run_partition_function(
    measure: Sequence[float],
    config: MFDFAConfig | None = None,
) -> MultifractalMethodResult:
    """Run a partition-function baseline over a positive measure.

    Example:
        `result = run_partition_function(volume_series, MFDFAConfig())`
    """
    active_config = config or MFDFAConfig()
    values = positive_measure(measure)
    probabilities = _normalize_measure(values)
    scales = resolve_method_scales(len(probabilities), active_config, "partition")
    functions = _partition_functions(probabilities, scales, active_config)
    return build_method_result(
        "partition_function",
        active_config,
        scales,
        functions,
        {"positive_measure": True},
        ("partition_function_baseline_not_wavelet_leader",),
    )


def _partition_functions(
    probabilities: Sequence[float],
    scales: Sequence[int],
    config: MFDFAConfig,
) -> dict[str, tuple[tuple[int, float], ...]]:
    return {
        q_label(q_value): tuple(
            (scale, _partition_value(probabilities, scale, q_value, config.epsilon))
            for scale in scales
        )
        for q_value in config.q_grid
    }


def _partition_value(
    probabilities: Sequence[float],
    scale: int,
    q_value: float,
    epsilon: float,
) -> float:
    masses = _box_masses(probabilities, scale)
    if q_value == 0.0:
        return float(sum(1 for mass in masses if mass > epsilon))
    if q_value == 1.0:
        entropy = -sum(mass * math.log(max(mass, epsilon)) for mass in masses)
        return math.exp(entropy)
    return max(sum(max(mass, epsilon) ** q_value for mass in masses), epsilon)


def _box_masses(probabilities: Sequence[float], scale: int) -> list[float]:
    return [
        sum(probabilities[start : start + scale])
        for start in range(0, len(probabilities) - scale + 1, scale)
    ]


def _normalize_measure(values: Sequence[float]) -> list[float]:
    total = sum(values)
    if total > 0.0:
        return [value / total for value in values]
    raise ValueError(f"Invalid measure total {total!r}; expected positive measure")
