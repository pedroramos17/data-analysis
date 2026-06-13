"""Train-only MarketLab shufflers."""

from __future__ import annotations

import random
from collections.abc import Sequence
from dataclasses import dataclass

from quant.services.marketlab.interfaces import BaseShuffler
from quant.services.marketlab.tda import LightweightTDAValidator


@dataclass(frozen=True, slots=True)
class ShuffleResult:
    """Split-aware shuffle result.

    Example:
        `ShuffleResult([2, 1], [3], [4], {})`
    """

    train_values: list[object]
    validation_values: list[object]
    test_values: list[object]
    metadata: dict[str, object]


class GeneralizedTimeWindowShuffle(BaseShuffler):
    """Shuffle only training values."""

    def __init__(self, seed: int = 0) -> None:
        self.seed = seed

    def shuffle(self, values: Sequence[object], window: object) -> ShuffleResult:
        """Return shuffled train values and untouched validation/test values."""
        train = _values_at(values, window.train_indices)
        random.Random(self.seed).shuffle(train)
        return _result(values, window, train, {"method": "generalized"})


class TemporalPatchShuffle(BaseShuffler):
    """Shuffle train patches while preserving shape."""

    def __init__(self, patch_size: int = 4) -> None:
        self.patch_size = max(1, patch_size)

    def shuffle(self, values: Sequence[object], window: object) -> ShuffleResult:
        """Return patch-reordered train values."""
        patches = _patches(_values_at(values, window.train_indices), self.patch_size)
        patches.reverse()
        return _result(values, window, _flatten(patches), {"method": "temporal_patch"})


class OverlapWindowShuffle(BaseShuffler):
    """Shuffle with overlap metadata preservation."""

    def __init__(self, overlap: int = 1) -> None:
        self.overlap = max(0, overlap)

    def shuffle(self, values: Sequence[object], window: object) -> ShuffleResult:
        """Return train values and preserve source index metadata."""
        train = _values_at(values, window.train_indices)
        metadata = {
            "method": "overlap",
            "source_index": window.metadata.get("index", []),
        }
        metadata["overlap"] = self.overlap
        return _result(values, window, train, metadata)


class IMFShuffle(BaseShuffler):
    """IMF shuffle with identity fallback when decomposition is unavailable."""

    def shuffle(self, values: Sequence[object], window: object) -> ShuffleResult:
        """Return no-op IMF fallback train values."""
        train = _values_at(values, window.train_indices)
        return _result(values, window, train, {"method": "imf_identity_fallback"})


class TopologyAwareShuffle(BaseShuffler):
    """Reject candidates that exceed topology-loss tolerance."""

    def __init__(self, max_topology_loss: float = 0.10) -> None:
        self.max_topology_loss = max_topology_loss
        self.validator = LightweightTDAValidator()

    def shuffle(
        self,
        values: Sequence[object],
        window: object,
        candidate_loss: float | None = None,
    ) -> ShuffleResult:
        """Return train values only when topology loss is acceptable."""
        train = _values_at(values, window.train_indices)
        loss = candidate_loss if candidate_loss is not None else 0.0
        _reject_high_loss(loss, self.max_topology_loss)
        metadata = {"method": "topology_aware", "loss": loss}
        return _result(values, window, train, metadata)


def _values_at(values: Sequence[object], indices: Sequence[int]) -> list[object]:
    return [values[index] for index in indices]


def _result(
    values: Sequence[object],
    window: object,
    train: list[object],
    metadata: dict[str, object],
) -> ShuffleResult:
    return ShuffleResult(
        train,
        _values_at(values, window.validation_indices),
        _values_at(values, window.test_indices),
        metadata,
    )


def _patches(values: Sequence[object], patch_size: int) -> list[list[object]]:
    return [
        list(values[index : index + patch_size])
        for index in range(0, len(values), patch_size)
    ]


def _flatten(patches: Sequence[Sequence[object]]) -> list[object]:
    return [value for patch in patches for value in patch]


def _reject_high_loss(loss: float, limit: float) -> None:
    if loss <= limit:
        return
    raise ValueError(f"Invalid topology loss {loss}; expected <= {limit}")
