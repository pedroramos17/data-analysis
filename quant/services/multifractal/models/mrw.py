"""Multifractal Random Walk research simulator."""

from __future__ import annotations

import math
import random
from collections.abc import Sequence
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class MRWParameters:
    """Parameters for a local MRW-style return simulator.

    Example:
        `params = MRWParameters(intermittency=0.1)`
    """

    intermittency: float = 0.1
    base_volatility: float = 0.01
    volatility_memory: float = 0.9

    def __post_init__(self) -> None:
        """Validate MRW simulator parameters."""
        _non_negative_float(self.intermittency, "intermittency")
        _positive_float(self.base_volatility, "base_volatility")
        _probability(self.volatility_memory, "volatility_memory")


@dataclass(frozen=True, slots=True)
class MRWSimulationResult:
    """MRW-style returns and latent volatility path.

    Example:
        `result = simulate_mrw_returns(MRWParameters(), 10, 7)`
    """

    returns: tuple[float, ...]
    volatility_path: tuple[float, ...]
    parameters: MRWParameters


@dataclass(frozen=True, slots=True)
class MRWIntermittencyEstimate:
    """Lightweight intermittency estimate for MRW diagnostics.

    Example:
        `estimate = estimate_mrw_intermittency(returns)`
    """

    intermittency: float
    method: str
    sample_size: int


def simulate_mrw_returns(
    parameters: MRWParameters,
    steps: int,
    seed: int,
) -> MRWSimulationResult:
    """Simulate MRW-like returns with log-volatility memory.

    Example:
        `result = simulate_mrw_returns(MRWParameters(), steps=20, seed=3)`
    """
    _positive_int(steps, "steps")
    chooser = random.Random(seed)
    log_volatility = 0.0
    returns: list[float] = []
    volatilities: list[float] = []
    for _step in range(steps):
        innovation = parameters.intermittency * chooser.gauss(0.0, 1.0)
        log_volatility = parameters.volatility_memory * log_volatility + innovation
        volatility = parameters.base_volatility * math.exp(log_volatility)
        volatilities.append(volatility)
        returns.append(chooser.gauss(0.0, volatility))
    return MRWSimulationResult(tuple(returns), tuple(volatilities), parameters)


def estimate_mrw_intermittency(series: Sequence[float]) -> MRWIntermittencyEstimate:
    """Estimate an intermittency proxy from log absolute returns.

    Example:
        `estimate = estimate_mrw_intermittency([0.01, -0.02, 0.03])`
    """
    values = _finite_series(series)
    log_abs = [math.log(abs(value) + 1e-12) for value in values]
    estimate = math.sqrt(max(_variance(log_abs), 0.0)) / math.sqrt(len(values))
    return MRWIntermittencyEstimate(
        estimate,
        "log_abs_return_scaling_proxy",
        len(values),
    )


def _finite_series(series: Sequence[float]) -> list[float]:
    if not series:
        raise ValueError(f"Invalid series {series!r}; expected finite numeric series")
    values = [float(value) for value in series]
    for value in values:
        if math.isfinite(value):
            continue
        raise ValueError(f"Invalid series value {value!r}; expected finite float")
    return values


def _variance(values: Sequence[float]) -> float:
    center = sum(values) / len(values)
    return sum((value - center) ** 2 for value in values) / len(values)


def _positive_int(value: int, label: str) -> None:
    if isinstance(value, int) and value > 0:
        return
    raise ValueError(f"Invalid {label} {value!r}; expected positive integer")


def _positive_float(value: float, label: str) -> None:
    if value > 0.0 and math.isfinite(value):
        return
    raise ValueError(f"Invalid {label} {value!r}; expected positive finite float")


def _non_negative_float(value: float, label: str) -> None:
    if value >= 0.0 and math.isfinite(value):
        return
    raise ValueError(f"Invalid {label} {value!r}; expected non-negative finite float")


def _probability(value: float, label: str) -> None:
    if 0.0 < value < 1.0:
        return
    raise ValueError(f"Invalid {label} {value!r}; expected probability in (0, 1)")
