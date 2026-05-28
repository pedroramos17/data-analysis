"""Search and validation constraints for symbolic formulas."""

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class SearchConstraints:
    """Bound random and evolved formulas.

    Example:
        `SearchConstraints(max_depth=3, max_operators=4)`
    """

    max_depth: int = 4
    max_operators: int = 6
    allowed_operands: tuple[str, ...] = ()
    allowed_windows: tuple[int, ...] = (1, 6, 24, 72)
    max_missing_ratio: float = 0.6
    min_unique_values: int = 2
    redundancy_threshold: float = 0.85
