"""Small online prediction helper around the stable model interface."""

from __future__ import annotations

from collections import deque
from collections.abc import Mapping
from dataclasses import dataclass, field

from src.models.base import BaseForecastModel, ForecastPrediction, row_symbol


@dataclass(slots=True)
class OnlinePredictionService:
    """Maintain a bounded per-symbol buffer and predict one event at a time.

    Example:
        `service.update({"symbol": "SPY", "close": 100}, "1d")`
    """

    model: BaseForecastModel
    window_size: int = 128
    _buffers: dict[str, deque[Mapping[str, object]]] = field(default_factory=dict)

    def update(
        self,
        row: Mapping[str, object],
        horizon: int | str,
    ) -> ForecastPrediction:
        """Append one row and return the latest model prediction."""
        symbol = row_symbol(row)
        buffer = self._buffers.setdefault(symbol, deque(maxlen=self.window_size))
        buffer.append(dict(row))
        predictions = self.model.predict(list(buffer), horizon)
        if predictions:
            return predictions[-1]
        raise ValueError("Invalid model output []; expected at least one prediction")

    def buffer_size(self, symbol: str) -> int:
        """Return current buffer size for a symbol."""
        return len(self._buffers.get(symbol, ()))
