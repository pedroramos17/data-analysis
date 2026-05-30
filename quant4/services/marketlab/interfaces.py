"""Base interfaces for MarketLab experimental components."""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Sequence


class BaseWindowBuilder(ABC):
    """Interface for leakage-safe window builders.

    Example:
        `builder.build(values, horizon=1)`
    """

    @abstractmethod
    def build(self, values: Sequence[object], horizon: int = 1) -> list[object]:
        """Build train/validation/test windows."""


class BaseShuffler(ABC):
    """Interface for train-only shufflers.

    Example:
        `shuffler.shuffle(values, window)`
    """

    @abstractmethod
    def shuffle(self, values: Sequence[object], window: object) -> object:
        """Shuffle train data while preserving validation/test data."""


class BaseTDAValidator(ABC):
    """Interface for topology-aware validation."""

    @abstractmethod
    def topology_loss(
        self,
        original: Sequence[float],
        candidate: Sequence[float],
    ) -> float:
        """Return topology loss for a candidate transform."""


class BaseSignatureEncoder(ABC):
    """Interface for signature encoders."""

    @abstractmethod
    def encode(self, values: Sequence[float]) -> list[float]:
        """Encode values as normalized signatures."""


class BaseDecomposer(ABC):
    """Interface for time-series decomposers."""

    @abstractmethod
    def decompose(self, values: Sequence[float]) -> object:
        """Decompose values and report reconstruction error."""


class BaseGraphBuilder(ABC):
    """Interface for graph snapshot builders."""

    @abstractmethod
    def build_snapshot(
        self,
        name: str,
        observations: Sequence[object],
        as_of: object,
    ) -> object:
        """Persist a graph snapshot through shared Quant4 models."""


class BaseGraphSampler(ABC):
    """Interface for graph samplers."""

    @abstractmethod
    def sample(self, nodes: Sequence[object]) -> list[object]:
        """Return sampled graph nodes."""


class BaseContrastiveLearner(ABC):
    """Interface for contrastive learners."""

    @abstractmethod
    def fit(self, rows: Sequence[object]) -> dict[str, object]:
        """Fit a local contrastive representation."""


class BaseForecastModel(ABC):
    """Interface for forecast models."""

    @abstractmethod
    def predict(self, rows: Sequence[object]) -> list[float]:
        """Return model predictions."""


class BaseSyntheticGenerator(ABC):
    """Interface for synthetic train-only generators."""

    @abstractmethod
    def generate(self, rows: Sequence[object]) -> list[object]:
        """Generate synthetic training rows."""


class BaseOptimizerFactory(ABC):
    """Interface for optimizer factories."""

    @abstractmethod
    def create(self, name: str, learning_rate: float) -> object:
        """Create an optimizer config."""


class BaseRegimeDetector(ABC):
    """Interface for MarketLab regime detectors."""

    @abstractmethod
    def detect(self, values: Sequence[float]) -> dict[str, object]:
        """Detect regimes from training-safe values."""


class BaseEvaluator(ABC):
    """Interface for benchmark evaluators."""

    @abstractmethod
    def evaluate(
        self,
        predictions: Sequence[float],
        labels: Sequence[float],
    ) -> dict[str, object]:
        """Return benchmark metrics."""
