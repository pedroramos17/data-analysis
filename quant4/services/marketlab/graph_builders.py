"""MarketLab graph builders backed by shared Quant4 GraphSnapshot."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import date

from quant4.services.marketlab.interfaces import BaseGraphBuilder
from quant4.services.registry import stable_config_hash


class CorrelationGraphBuilder(BaseGraphBuilder):
    """Persist a lightweight past-only graph snapshot."""

    def build_snapshot(
        self,
        name: str,
        observations: Sequence[tuple[date, float]],
        as_of: date,
    ) -> object:
        """Build a graph snapshot using observations at or before `as_of`."""
        from quant4.models import GraphSnapshot

        past = [(stamp, value) for stamp, value in observations if stamp <= as_of]
        config = {"engine": "marketlab", "builder": "correlation_graph"}
        return GraphSnapshot.objects.create(
            name=name,
            component_name="marketlab_correlation_graph",
            config_json=config,
            config_hash=stable_config_hash(config),
            random_seed=0,
            data_start=_first_date(past),
            data_end=_last_date(past),
            node_count=len(past),
            edge_count=max(0, len(past) - 1),
            feature_schema_json=_graph_feature_schema(),
            metrics_json={"max_observation_date": _date_text(_last_date(past))},
            provenance_json={"engine": "marketlab"},
            status="RESEARCH_ONLY",
        )


def _first_date(observations: Sequence[tuple[date, float]]) -> date | None:
    return observations[0][0] if observations else None


def _last_date(observations: Sequence[tuple[date, float]]) -> date | None:
    return observations[-1][0] if observations else None


def _date_text(value: date | None) -> str:
    return "" if value is None else value.isoformat()


def _graph_feature_schema() -> dict[str, object]:
    return {
        "inputs": ["date", "value"],
        "fit_scope": "past_observations_at_or_before_as_of",
    }
