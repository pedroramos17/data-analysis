"""Validation helpers for finance statistical functions."""

from __future__ import annotations


def clamp_correlation(value: float, epsilon: float = 1e-12) -> float:
    """Clamp a candidate correlation inside the open interval.

    Example:
        `clamp_correlation(2.0)`
    """
    return max(-1.0 + epsilon, min(1.0 - epsilon, float(value)))


def require_non_negative(value: float, label: str) -> float:
    """Return a non-negative value or raise with offending input.

    Example:
        `require_non_negative(1.0, "variance")`
    """
    if value >= 0:
        return float(value)
    raise ValueError(f"Invalid {label}={value!r}; expected non-negative number")
