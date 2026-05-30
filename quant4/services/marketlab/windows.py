"""Leakage-safe MarketLab window builders."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from quant4.services.marketlab.interfaces import BaseWindowBuilder


@dataclass(frozen=True, slots=True)
class MarketWindow:
    """Train/validation/test indices plus metadata.

    Example:
        `MarketWindow([0, 1], [3], [4], {"embargo": 1})`
    """

    train_indices: list[int]
    validation_indices: list[int]
    test_indices: list[int]
    metadata: dict[str, object]


class RollingWindowBuilder(BaseWindowBuilder):
    """Build fixed-length rolling windows."""

    def __init__(self, train_size: int, test_size: int) -> None:
        self.train_size = train_size
        self.test_size = test_size

    def build(self, values: Sequence[object], horizon: int = 1) -> list[MarketWindow]:
        """Return rolling windows without future leakage."""
        return _rolling_windows(
            len(values),
            self.train_size,
            self.test_size,
            horizon,
            0,
        )


class ExpandingWindowBuilder(BaseWindowBuilder):
    """Build expanding train windows."""

    def __init__(self, min_train_size: int, test_size: int) -> None:
        self.min_train_size = min_train_size
        self.test_size = test_size

    def build(self, values: Sequence[object], horizon: int = 1) -> list[MarketWindow]:
        """Return expanding windows without future leakage."""
        return _expanding_windows(
            len(values),
            self.min_train_size,
            self.test_size,
            horizon,
        )


class PurgedWalkForwardWindowBuilder(BaseWindowBuilder):
    """Build purged walk-forward validation windows with embargo."""

    def __init__(self, train_size: int, test_size: int, embargo: int) -> None:
        self.train_size = train_size
        self.test_size = test_size
        self.embargo = embargo

    def build(self, values: Sequence[object], horizon: int = 1) -> list[MarketWindow]:
        """Return purged windows that leave an embargo gap."""
        return _rolling_windows(
            len(values),
            self.train_size,
            self.test_size,
            horizon,
            self.embargo,
        )


def horizon_aware_labels(
    values: Sequence[float],
    horizon: int,
) -> list[dict[str, object]]:
    """Create labels from future horizon while keeping feature indices explicit."""
    labels: list[dict[str, object]] = []
    for index in range(max(0, len(values) - horizon)):
        labels.append(_label_row(values, index, horizon))
    return labels


def persist_window_artifact(
    name: str,
    window: MarketWindow,
    config: dict[str, object] | None = None,
) -> object:
    """Persist a MarketLab window using shared Quant4 WindowArtifact."""
    from quant4.models import WindowArtifact
    from quant4.services.registry import stable_config_hash

    config_json = config or {"engine": "marketlab"}
    return WindowArtifact.objects.create(
        name=name,
        config_json=config_json,
        config_hash=stable_config_hash(config_json),
        random_seed=0,
        split_metadata_json=_split_metadata(window),
        provenance_json={"engine": "marketlab"},
    )


def _rolling_windows(
    length: int,
    train_size: int,
    test_size: int,
    horizon: int,
    embargo: int,
) -> list[MarketWindow]:
    windows: list[MarketWindow] = []
    stop = _window_stop(length, train_size, test_size, horizon, embargo)
    for train_start in range(0, stop):
        window = _rolling_window(
            train_start,
            train_size,
            test_size,
            horizon,
            embargo,
            length,
        )
        windows.append(window)
    return windows


def _rolling_window(
    train_start: int,
    train_size: int,
    test_size: int,
    horizon: int,
    embargo: int,
    length: int,
) -> MarketWindow:
    train = list(range(train_start, train_start + train_size))
    validation_start = train[-1] + max(1, horizon) + embargo
    validation = list(range(validation_start, validation_start + test_size))
    test_start = validation[-1] + 1
    test = list(range(test_start, min(length, test_start + test_size)))
    metadata = {"horizon": horizon, "embargo": embargo}
    return MarketWindow(train, validation, test, metadata)


def _expanding_windows(
    length: int,
    min_train_size: int,
    test_size: int,
    horizon: int,
) -> list[MarketWindow]:
    windows: list[MarketWindow] = []
    for train_end in range(min_train_size - 1, length - horizon - test_size):
        validation_start = train_end + horizon
        validation = list(range(validation_start, validation_start + test_size))
        test_start = validation[-1] + 1
        test = list(range(test_start, min(length, test_start + test_size)))
        windows.append(MarketWindow(list(range(train_end + 1)), validation, test, {}))
    return windows


def _window_stop(
    length: int,
    train_size: int,
    test_size: int,
    horizon: int,
    embargo: int,
) -> int:
    return max(0, length - train_size - horizon - embargo - test_size + 1)


def _label_row(values: Sequence[float], index: int, horizon: int) -> dict[str, object]:
    return {
        "feature_index": index,
        "label_index": index + horizon,
        "label": float(values[index + horizon]) - float(values[index]),
    }


def _split_metadata(window: MarketWindow) -> dict[str, object]:
    return {
        "train_indices": window.train_indices,
        "validation_indices": window.validation_indices,
        "test_indices": window.test_indices,
        "metadata": window.metadata,
    }
