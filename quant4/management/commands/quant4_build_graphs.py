"""Build Quant4 graph snapshots from local JSON series."""

from __future__ import annotations

import json
from datetime import date

from django.core.management.base import BaseCommand, CommandParser

from quant4.services.graphs.graph_builders import (
    CorrelationGraphBuilder,
    DynamicSparseGraphBuilder,
    GraphBuildResult,
    GraphSeries,
    IMFCoherenceGraphBuilder,
    LeadLagSignatureGraphBuilder,
    MutualInformationGraphBuilder,
    PartialCorrelationGraphBuilder,
    TDAComplexityGraphBuilder,
)
from quant4.services.graphs.graph_sampling import persist_graph_snapshot


class Command(BaseCommand):
    """Persist a local Quant4 graph snapshot."""

    help = "Build leakage-safe Quant4 graph snapshots from local JSON series."

    def add_arguments(self, parser: CommandParser) -> None:
        """Register graph build options."""
        parser.add_argument("--name", default="quant4-graph")
        parser.add_argument("--series-json", required=True)
        parser.add_argument("--window-end", required=True)
        parser.add_argument("--output-dir", default="data/quant4_graphs")
        parser.add_argument("--builder", default="correlation")
        parser.add_argument("--random-seed", type=int, default=0)

    def handle(self, *args: object, **options: object) -> None:
        """Build and persist a shared GraphSnapshot."""
        window_end = date.fromisoformat(str(options["window_end"]))
        series = _parse_series(options["series_json"])
        result = _builder(str(options["builder"])).build(series, window_end)
        snapshot = persist_graph_snapshot(
            name=str(options["name"]),
            result=_with_window_end(result, window_end),
            output_dir=str(options["output_dir"]),
            data_range=_data_range(series, window_end),
            split_range=(window_end, window_end),
            random_seed=int(options["random_seed"]),
            provenance={"command": "quant4_build_graphs"},
        )
        self.stdout.write(f"graph_snapshot_id={snapshot.pk}")


def _parse_series(raw_value: object) -> GraphSeries:
    parsed = json.loads(str(raw_value))
    if not isinstance(parsed, dict):
        raise ValueError(f"Invalid series {parsed!r}; expected object of symbol rows")
    return {str(symbol): _parse_rows(rows, symbol) for symbol, rows in parsed.items()}


def _parse_rows(rows: object, symbol: object) -> list[tuple[date, float]]:
    if not isinstance(rows, list):
        raise ValueError(f"Invalid rows for {symbol!r} {rows!r}; expected list")
    return [_parse_row(row, symbol) for row in rows]


def _parse_row(row: object, symbol: object) -> tuple[date, float]:
    if not isinstance(row, list) or len(row) != 2:
        raise ValueError(f"Invalid row for {symbol!r} {row!r}; expected [date, value]")
    return date.fromisoformat(str(row[0])), float(row[1])


def _builder(name: str) -> object:
    builders = {
        "correlation": CorrelationGraphBuilder,
        "partial_correlation": PartialCorrelationGraphBuilder,
        "mutual_information": MutualInformationGraphBuilder,
        "lead_lag_signature": LeadLagSignatureGraphBuilder,
        "imf_coherence": IMFCoherenceGraphBuilder,
        "tda_complexity": TDAComplexityGraphBuilder,
        "dynamic_sparse": DynamicSparseGraphBuilder,
    }
    if name in builders:
        return builders[name]()
    raise ValueError(f"Invalid builder {name!r}; expected one of {sorted(builders)}")


def _with_window_end(result: GraphBuildResult, window_end: date) -> GraphBuildResult:
    metadata = dict(result.metadata) | {"max_observation_date": window_end.isoformat()}
    return GraphBuildResult(result.nodes, result.edges, result.adjacency, metadata)


def _data_range(series: GraphSeries, window_end: date) -> tuple[date, date]:
    dates = [
        stamp
        for observations in series.values()
        for stamp, _value in observations
        if stamp <= window_end
    ]
    start = min(dates) if dates else window_end
    return start, window_end
