"""Event-driven alpha hypothesis data structures."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Mapping


@dataclass(frozen=True)
class AlphaCandidate:
    """A testable event-driven alpha candidate."""

    candidate_id: str
    hypothesis: str
    direction: str
    entry_horizon: str
    exit_horizon: str
    event_id: str
    subject_entity_id: str
    confidence: Decimal
    reasoning_trail: tuple[Mapping[str, object], ...]
    backtest_spec: Mapping[str, object]
    assumptions_used: tuple[str, ...] = ("event_effect_is_testable_not_tradable",)

    def to_backtest_spec(self) -> dict[str, object]:
        return {
            "candidate_id": self.candidate_id,
            "direction": self.direction,
            "entry_horizon": self.entry_horizon,
            "exit_horizon": self.exit_horizon,
            "event_id": self.event_id,
            "subject_entity_id": self.subject_entity_id,
            **dict(self.backtest_spec),
        }
