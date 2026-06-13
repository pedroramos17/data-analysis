"""Graph/relationship proxy feature group."""

from __future__ import annotations

from collections.abc import Mapping, Sequence

from src.pipeline.features.base import feature_row, float_or_none, group_symbol_timeframe, rolling_std

FEATURE_SET = "graph"
FEATURE_COLUMNS = (
    "correlation_degree_proxy",
    "market_centrality_proxy",
    "sector_relation_proxy",
    "event_relation_proxy",
    "graph_embedding_placeholder",
)


def compute_graph_features(
    rows: Sequence[Mapping[str, object]],
    *,
    version: str,
    window: int = 20,
) -> list[dict[str, object]]:
    """Compute deterministic graph placeholders from market co-movement."""
    groups = group_symbol_timeframe(rows)
    universe_size = max(len({key[0] for key in groups}), 1)
    output: list[dict[str, object]] = []
    for group_rows in groups.values():
        closes = [float_or_none(row.get("close")) for row in group_rows]
        returns = _simple_returns(closes)
        for index, row in enumerate(group_rows):
            volatility = rolling_std(returns, index, window)
            values = {
                "correlation_degree_proxy": 1.0 / universe_size,
                "market_centrality_proxy": 1.0 / (1.0 + volatility) if volatility is not None else None,
                "sector_relation_proxy": 0.0,
                "event_relation_proxy": 0.0,
                "graph_embedding_placeholder": 0.0,
            }
            output.append(feature_row(row, FEATURE_SET, version, values))
    return output


def graph_sql(version: str) -> str:
    """Return DuckDB SQL sketch for graph proxy features."""
    return f"""
    select
        'graph' as feature_set,
        '{version}' as version,
        symbol,
        asset_type,
        ts,
        timeframe,
        1.0 / count(distinct symbol) over (partition by timeframe, ts) as correlation_degree_proxy,
        0.0 as market_centrality_proxy,
        0.0 as sector_relation_proxy,
        0.0 as event_relation_proxy,
        0.0 as graph_embedding_placeholder
    from input_rows
    """.strip()


def _simple_returns(closes: Sequence[float | None]) -> list[float | None]:
    output: list[float | None] = []
    previous: float | None = None
    for close in closes:
        if close is not None and previous not in (None, 0):
            output.append(close / previous - 1.0)
        else:
            output.append(None)
        if close is not None:
            previous = close
    return output
