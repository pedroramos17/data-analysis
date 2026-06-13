"""Multifractal Model of Asset Returns research simulator."""

from __future__ import annotations

import math
import random
from collections.abc import Sequence
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class MMARParameters:
    """Parameters for a lightweight MMAR-style simulator.

    Example:
        `params = MMARParameters(base_volatility=0.02)`
    """

    base_volatility: float = 0.01
    intermittency: float = 0.15
    deformation_persistence: float = 0.85

    def __post_init__(self) -> None:
        """Validate MMAR simulator parameters."""
        _positive_float(self.base_volatility, "base_volatility")
        _non_negative_float(self.intermittency, "intermittency")
        _probability(self.deformation_persistence, "deformation_persistence")


@dataclass(frozen=True, slots=True)
class MMARSimulationResult:
    """MMAR-style simulated returns and trading-time deformation.

    Example:
        `result = simulate_mmar_returns(MMARParameters(), 10, 7)`
    """

    returns: tuple[float, ...]
    time_deformation: tuple[float, ...]
    parameters: MMARParameters


@dataclass(frozen=True, slots=True)
class MMARCalibrationReport:
    """Explicit placeholder for future full MMAR calibration.

    Example:
        `report = calibrate_mmar_placeholder(returns)`
    """

    status: str
    message: str
    sample_size: int
    variance_proxy: float


def simulate_mmar_returns(
    parameters: MMARParameters,
    steps: int,
    seed: int,
) -> MMARSimulationResult:
    """Simulate returns under a stochastic trading-time deformation.

    Example:
        `result = simulate_mmar_returns(MMARParameters(), steps=20, seed=5)`
    """
    _positive_int(steps, "steps")
    chooser = random.Random(seed)
    deformation = _time_deformation(parameters, steps, chooser)
    returns = [
        chooser.gauss(0.0, parameters.base_volatility * math.sqrt(value))
        for value in deformation
    ]
    return MMARSimulationResult(tuple(returns), tuple(deformation), parameters)


def calibrate_mmar_placeholder(series: Sequence[float]) -> MMARCalibrationReport:
    """Return an explicit placeholder instead of overclaiming MMAR calibration.

    Example:
        `report = calibrate_mmar_placeholder([0.01, -0.02])`
    """
    values = _finite_series(series)
    return MMARCalibrationReport(
        "CALIBRATION_PLACEHOLDER",
        "Research interface only; not full MMAR calibration.",
        len(values),
        _variance(values),
    )


def _time_deformation(
    parameters: MMARParameters,
    steps: int,
    chooser: random.Random,
) -> list[float]:
    deformation: list[float] = []
    state = 1.0
    for _step in range(steps):
        innovation = math.exp(parameters.intermittency * chooser.gauss(0.0, 1.0))
        state = parameters.deformation_persistence * state
        state += (1.0 - parameters.deformation_persistence) * innovation
        deformation.append(max(state, 1e-12))
    return deformation


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
