"""Markov-Switching Multifractal volatility research model."""

from __future__ import annotations

import math
import random
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class MSMParameters:
    """Parameters for a binomial MSM volatility simulator.

    Example:
        `params = MSMParameters(component_count=3, base_volatility=0.02)`
    """

    component_count: int = 4
    base_volatility: float = 0.01
    low_multiplier: float = 0.7
    high_multiplier: float = 1.3
    switch_probability: float = 0.12

    def __post_init__(self) -> None:
        """Validate MSM parameters after dataclass creation."""
        _positive_int(self.component_count, "component_count")
        _positive_float(self.base_volatility, "base_volatility")
        _positive_float(self.low_multiplier, "low_multiplier")
        _positive_float(self.high_multiplier, "high_multiplier")
        _probability(self.switch_probability, "switch_probability")


@dataclass(frozen=True, slots=True)
class MSMSimulationResult:
    """MSM simulated return path with latent volatility state.

    Example:
        `result = simulate_msm_returns(params, steps=100, seed=7)`
    """

    returns: tuple[float, ...]
    volatility_path: tuple[float, ...]
    latent_states: tuple[tuple[int, ...], ...]
    parameters: MSMParameters


@dataclass(frozen=True, slots=True)
class MSMVolatilityForecast:
    """Distribution summary for MSM volatility forecasts.

    Example:
        `forecast = forecast_msm_volatility_distribution(params, 5, 100, 7)`
    """

    horizon: int
    path_count: int
    quantiles: dict[str, float]
    mean_volatility: float
    parameters: MSMParameters


def simulate_msm_returns(
    parameters: MSMParameters,
    steps: int,
    seed: int,
) -> MSMSimulationResult:
    """Simulate MSM returns from a seeded binomial multiplier process.

    Example:
        `result = simulate_msm_returns(MSMParameters(), steps=10, seed=1)`
    """
    _positive_int(steps, "steps")
    chooser = random.Random(seed)
    states = _initial_states(parameters, chooser)
    returns: list[float] = []
    volatilities: list[float] = []
    latent_states: list[tuple[int, ...]] = []
    for _step in range(steps):
        states = _transition_states(states, parameters, chooser)
        volatility = _state_volatility(states, parameters)
        volatilities.append(volatility)
        latent_states.append(tuple(states))
        returns.append(chooser.gauss(0.0, volatility))
    return MSMSimulationResult(
        tuple(returns),
        tuple(volatilities),
        tuple(latent_states),
        parameters,
    )


def forecast_msm_volatility_distribution(
    parameters: MSMParameters,
    horizon: int,
    path_count: int,
    seed: int,
) -> MSMVolatilityForecast:
    """Forecast MSM volatility distribution with seeded Monte Carlo paths.

    Example:
        `forecast = forecast_msm_volatility_distribution(params, 10, 100, 3)`
    """
    _positive_int(horizon, "horizon")
    _positive_int(path_count, "path_count")
    terminal_vols = [
        simulate_msm_returns(parameters, horizon, seed + path_index).volatility_path[-1]
        for path_index in range(path_count)
    ]
    return MSMVolatilityForecast(
        horizon,
        path_count,
        {
            "p05": _percentile(terminal_vols, 0.05),
            "p50": _percentile(terminal_vols, 0.50),
            "p95": _percentile(terminal_vols, 0.95),
        },
        sum(terminal_vols) / len(terminal_vols),
        parameters,
    )


def _initial_states(parameters: MSMParameters, chooser: random.Random) -> list[int]:
    return [chooser.choice([0, 1]) for _index in range(parameters.component_count)]


def _transition_states(
    states: list[int],
    parameters: MSMParameters,
    chooser: random.Random,
) -> list[int]:
    return [
        chooser.choice([0, 1])
        if chooser.random() < parameters.switch_probability
        else state
        for state in states
    ]


def _state_volatility(states: list[int], parameters: MSMParameters) -> float:
    multiplier = 1.0
    for state in states:
        multiplier *= parameters.high_multiplier if state else parameters.low_multiplier
    return parameters.base_volatility * math.sqrt(multiplier)


def _percentile(values: list[float], quantile: float) -> float:
    ordered = sorted(values)
    position = quantile * (len(ordered) - 1)
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return ordered[lower]
    return ordered[lower] + (ordered[upper] - ordered[lower]) * (position - lower)


def _positive_int(value: int, label: str) -> None:
    if isinstance(value, int) and value > 0:
        return
    raise ValueError(f"Invalid {label} {value!r}; expected positive integer")


def _positive_float(value: float, label: str) -> None:
    if value > 0.0 and math.isfinite(value):
        return
    raise ValueError(f"Invalid {label} {value!r}; expected positive finite float")


def _probability(value: float, label: str) -> None:
    if 0.0 < value < 1.0:
        return
    raise ValueError(f"Invalid {label} {value!r}; expected probability in (0, 1)")
