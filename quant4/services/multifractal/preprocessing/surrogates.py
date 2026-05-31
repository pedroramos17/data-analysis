"""Surrogate generators for multifractal diagnostics."""

from __future__ import annotations

import cmath
import math
import random
from collections.abc import Sequence

from quant4.services.multifractal.preprocessing._series import (
    _coerce_finite_series,
    _mean,
    _positive_int,
)


def shuffled_returns(values: Sequence[float], seed: int) -> list[float]:
    """Return a seeded full shuffle preserving the empirical distribution.

    Example:
        `sample = shuffled_returns([1.0, 2.0, 3.0], seed=7)`
    """
    shuffled = _coerce_finite_series(values, "values")
    random.Random(seed).shuffle(shuffled)
    return shuffled


def block_shuffled_returns(
    values: Sequence[float],
    block_size: int,
    seed: int,
) -> list[float]:
    """Shuffle contiguous blocks while preserving within-block order.

    Example:
        `sample = block_shuffled_returns([1.0, 2.0, 3.0, 4.0], 2, 7)`
    """
    validated = _coerce_finite_series(values, "values")
    _positive_int(block_size, "block_size")
    blocks = [
        validated[index : index + block_size]
        for index in range(0, len(validated), block_size)
    ]
    random.Random(seed).shuffle(blocks)
    return [value for block in blocks for value in block]


def phase_randomized_surrogate(values: Sequence[float], seed: int) -> list[float]:
    """Return a Fourier phase surrogate using a pure-Python DFT.

    Example:
        `sample = phase_randomized_surrogate([1.0, 2.0, 3.0, 4.0], seed=7)`
    """
    validated = _coerce_finite_series(values, "values")
    if len(validated) < 4:
        return list(reversed(validated))
    coefficients = _dft([value - _mean(validated) for value in validated])
    randomized = _randomize_coefficients(coefficients, seed)
    return [value + _mean(validated) for value in _inverse_dft(randomized)]


def iaaft_surrogate(
    values: Sequence[float],
    seed: int,
    iterations: int = 10,
) -> list[float]:
    """Return a lightweight IAAFT-style surrogate with rank distribution matching.

    Example:
        `sample = iaaft_surrogate([1.0, 2.0, 3.0, 4.0], seed=7)`
    """
    _positive_int(iterations, "iterations")
    validated = _coerce_finite_series(values, "values")
    candidate = phase_randomized_surrogate(validated, seed)
    for offset in range(iterations):
        matched = _match_distribution(candidate, validated)
        candidate = phase_randomized_surrogate(matched, seed + offset + 1)
    return _match_distribution(candidate, validated)


def bootstrap_sample(
    values: Sequence[float],
    sample_size: int,
    seed: int,
) -> list[float]:
    """Draw a seeded bootstrap sample with replacement.

    Example:
        `sample = bootstrap_sample([1.0, 2.0], 10, seed=3)`
    """
    validated = _coerce_finite_series(values, "values")
    _positive_int(sample_size, "sample_size")
    chooser = random.Random(seed)
    return [chooser.choice(validated) for _index in range(sample_size)]


def lag_one_autocorrelation(values: Sequence[float]) -> float:
    """Estimate circular lag-one autocorrelation for surrogate diagnostics.

    Example:
        `rho = lag_one_autocorrelation([1.0, 2.0, 3.0])`
    """
    validated = _coerce_finite_series(values, "values")
    center = _mean(validated)
    denominator = sum((value - center) ** 2 for value in validated)
    if denominator == 0.0:
        return 0.0
    return _circular_lag_covariance(validated, center) / denominator


def _dft(values: Sequence[float]) -> list[complex]:
    length = len(values)
    return [
        sum(
            value * cmath.exp(-2j * math.pi * frequency * index / length)
            for index, value in enumerate(values)
        )
        for frequency in range(length)
    ]


def _inverse_dft(coefficients: Sequence[complex]) -> list[float]:
    length = len(coefficients)
    return [
        (
            sum(
                coefficient * cmath.exp(2j * math.pi * frequency * index / length)
                for frequency, coefficient in enumerate(coefficients)
            )
            / length
        ).real
        for index in range(length)
    ]


def _randomize_coefficients(
    coefficients: Sequence[complex],
    seed: int,
) -> list[complex]:
    randomized = [0j for _coefficient in coefficients]
    randomized[0] = coefficients[0]
    _copy_nyquist_coefficient(coefficients, randomized)
    _fill_randomized_pairs(coefficients, randomized, random.Random(seed))
    return randomized


def _copy_nyquist_coefficient(
    coefficients: Sequence[complex],
    randomized: list[complex],
) -> None:
    if len(coefficients) % 2 == 0:
        randomized[len(coefficients) // 2] = coefficients[len(coefficients) // 2]


def _fill_randomized_pairs(
    coefficients: Sequence[complex],
    randomized: list[complex],
    chooser: random.Random,
) -> None:
    for frequency in range(1, (len(coefficients) + 1) // 2):
        phase = chooser.uniform(0.0, 2.0 * math.pi)
        coefficient = abs(coefficients[frequency]) * complex(
            math.cos(phase),
            math.sin(phase),
        )
        randomized[frequency] = coefficient
        randomized[-frequency] = coefficient.conjugate()


def _match_distribution(
    candidate: Sequence[float],
    target: Sequence[float],
) -> list[float]:
    ordered_target = sorted(target)
    ranked_positions = sorted(range(len(candidate)), key=lambda index: candidate[index])
    matched = [0.0 for _value in candidate]
    for rank, index in enumerate(ranked_positions):
        matched[index] = ordered_target[rank]
    return matched


def _circular_lag_covariance(values: Sequence[float], center: float) -> float:
    return sum(
        (value - center) * (values[(index + 1) % len(values)] - center)
        for index, value in enumerate(values)
    )
