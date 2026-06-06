"""DuckDB SQL generation for the Quant MVP feature store."""

from __future__ import annotations

from collections.abc import Sequence

from src.features.definitions import DEFAULT_FEATURE_GROUPS, FEATURE_GROUPS
from src.warehouse.duckdb_context import sql_literal


def feature_store_sql(
    *,
    version: str,
    groups: Sequence[str] = DEFAULT_FEATURE_GROUPS,
    universe: Sequence[str] = (),
    start: str = "1900-01-01",
    end: str = "2999-12-31",
    timeframe: str = "1d",
) -> str:
    """Return DuckDB SQL that emits long-form versioned feature rows."""
    selected_groups = _validate_groups(groups)
    feature_selects = [
        select_sql
        for group in selected_groups
        for select_sql in FEATURE_SELECTS[group](version)
    ]
    return f"""
with
bars as ({_bars_sql(universe, start, end, timeframe)}),
ordered as ({_ordered_sql()}),
price_base as ({_price_base_sql()}),
price_enriched as ({_price_enriched_sql()}),
market_returns as ({_market_returns_sql()}),
risk_base as ({_risk_base_sql()}),
risk_enriched as ({_risk_enriched_sql()}),
lob_base as ({_lob_base_sql(universe, start, end, timeframe)}),
lob_enriched as ({_lob_enriched_sql()}),
all_features as (
    {' union all '.join(feature_selects)}
)
select *
from all_features
where feature_value is not null
order by symbol, ts, feature_set, feature_name
""".strip()


def _bars_sql(
    universe: Sequence[str],
    start: str,
    end: str,
    timeframe: str,
) -> str:
    filters = _base_filters(universe, start, end, timeframe)
    return f"""
    select symbol, asset_type, ts, timeframe, open, high, low, close, volume, source
    from v_market_bars
    where {' and '.join(filters)}
    """.strip()


def _lob_base_sql(
    universe: Sequence[str],
    start: str,
    end: str,
    timeframe: str,
) -> str:
    filters = _base_filters(universe, start, end, timeframe)
    return f"""
    select symbol, asset_type, ts, timeframe, spread, imbalance, bid_depth, ask_depth, source
    from v_lob_features
    where {' and '.join(filters)}
    """.strip()


def _base_filters(
    universe: Sequence[str],
    start: str,
    end: str,
    timeframe: str,
) -> list[str]:
    filters = [
        f"ts >= cast({sql_literal(start)} as timestamp)",
        f"ts <= cast({sql_literal(end)} as timestamp)",
        f"timeframe = {sql_literal(timeframe)}",
    ]
    if universe:
        values = ", ".join(sql_literal(symbol.upper()) for symbol in universe)
        filters.append(f"upper(symbol) in ({values})")
    return filters


def _ordered_sql() -> str:
    return """
    select
        *,
        lag(close) over w as previous_close,
        lag(close, 5) over w as close_5,
        lag(close, 20) over w as close_20,
        lag(volume) over w as previous_volume,
        avg(close) over w20 as average_close_20,
        max(close) over w60 as peak_close_60,
        avg(volume) over w20 as average_volume_20
    from bars
    window
        w as (partition by symbol, timeframe order by ts),
        w20 as (partition by symbol, timeframe order by ts rows between 19 preceding and current row),
        w60 as (partition by symbol, timeframe order by ts rows between 59 preceding and current row)
    """.strip()


def _price_base_sql() -> str:
    return """
    select
        *,
        close / nullif(previous_close, 0) - 1.0 as returns,
        case
            when close > 0 and previous_close > 0 then ln(close / previous_close)
            else NULL
        end as log_returns,
        close / nullif(close_20, 0) - 1.0 as momentum,
        average_close_20 / nullif(close, 0) - 1.0 as mean_reversion,
        close / nullif(peak_close_60, 0) - 1.0 as drawdown,
        (volume - average_volume_20) / nullif(average_volume_20, 0) as volume_imbalance
    from ordered
    """.strip()


def _price_enriched_sql() -> str:
    return """
    select
        *,
        stddev_samp(log_returns) over w20 as rolling_volatility,
        sqrt(avg(pow(log_returns, 2)) over w20) as realized_volatility,
        volume / nullif(abs(log_returns), 0) as liquidity_proxy,
        stddev_samp(log_returns) over w60 as volatility_60,
        avg(abs(log_returns)) over w20 as average_abs_return_20,
        avg(abs(log_returns)) over w60 as average_abs_return_60,
        avg(pow(log_returns, 2)) over w20 as second_moment_20,
        avg(pow(log_returns, 4)) over w20 as fourth_moment_20,
        quantile_cont(log_returns, 0.05) over w60 as var_95
    from price_base
    window
        w20 as (partition by symbol, timeframe order by ts rows between 19 preceding and current row),
        w60 as (partition by symbol, timeframe order by ts rows between 59 preceding and current row)
    """.strip()


def _market_returns_sql() -> str:
    return """
    select timeframe, ts, avg(log_returns) as market_log_return
    from price_enriched
    group by timeframe, ts
    """.strip()


def _risk_base_sql() -> str:
    return """
    select
        price_enriched.*,
        market_returns.market_log_return,
        covar_samp(log_returns, market_log_return) over w60 as covariance,
        var_samp(market_log_return) over w60 as market_variance,
        corr(log_returns, market_log_return) over w60 as correlation,
        avg(drawdown) over w60 as expected_drawdown,
        min(drawdown) over w60 as max_drawdown
    from price_enriched
    left join market_returns using (timeframe, ts)
    window w60 as (
        partition by symbol, timeframe order by ts rows between 59 preceding and current row
    )
    """.strip()


def _risk_enriched_sql() -> str:
    return """
    select
        *,
        covariance / nullif(market_variance, 0) as rolling_beta,
        avg(case when log_returns <= var_95 then log_returns else NULL end) over w60 as cvar_95,
        abs(var_95 - avg(case when log_returns <= var_95 then log_returns else NULL end) over w60) as tail_risk,
        1.0 / nullif(liquidity_proxy, 0) as liquidity_risk,
        case when rolling_volatility > volatility_60 then 1.0 else 0.0 end as volatility_regime,
        case when momentum > 0 then 1.0 when momentum < 0 then -1.0 else 0.0 end as trend_regime,
        case when abs(correlation) > 0.6 then 1.0 else 0.0 end as correlation_regime,
        case when liquidity_proxy < avg(liquidity_proxy) over w60 then 1.0 else 0.0 end as liquidity_regime
    from risk_base
    window w60 as (
        partition by symbol, timeframe order by ts rows between 59 preceding and current row
    )
    """.strip()


def _lob_enriched_sql() -> str:
    return """
    select
        *,
        imbalance as order_imbalance,
        (bid_depth - ask_depth) / nullif(bid_depth + ask_depth, 0) as depth_imbalance,
        spread / nullif(bid_depth + ask_depth, 0) as slope,
        imbalance * (bid_depth + ask_depth) as queue_pressure,
        stddev_samp(spread) over (
            partition by symbol, timeframe order by ts rows between 4 preceding and current row
        ) as short_horizon_realized_volatility,
        cast(NULL as DOUBLE) as mid_price,
        cast(NULL as DOUBLE) as microprice
    from lob_base
    """.strip()


def _feature_select(
    source: str,
    group: str,
    version: str,
    name: str,
    expression: str,
) -> str:
    return f"""
    select
        symbol,
        asset_type,
        ts,
        timeframe,
        {sql_literal(group)} as feature_set,
        {sql_literal(version)} as version,
        {sql_literal(name)} as feature_name,
        cast({expression} as DOUBLE) as feature_value,
        cast('{{}}' as VARCHAR) as values_json,
        'phase10_feature_pipeline' as source
    from {source}
    """.strip()


def _price_volume_selects(version: str) -> list[str]:
    return [
        _feature_select("price_enriched", "price_volume", version, name, name)
        for name in (
            "returns",
            "log_returns",
            "rolling_volatility",
            "realized_volatility",
            "momentum",
            "mean_reversion",
            "drawdown",
            "liquidity_proxy",
            "volume_imbalance",
        )
    ]


def _lob_selects(version: str) -> list[str]:
    return [
        _feature_select("lob_enriched", "lob", version, name, name)
        for name in (
            "spread",
            "mid_price",
            "microprice",
            "order_imbalance",
            "depth_imbalance",
            "slope",
            "queue_pressure",
            "short_horizon_realized_volatility",
        )
    ]


def _multifractal_selects(version: str) -> list[str]:
    expressions = {
        "generalized_hurst_exponent": "greatest(0.0, least(1.0, 0.5 + coalesce(average_abs_return_20 - average_abs_return_60, 0)))",
        "mf_dfa_features": "rolling_volatility / nullif(volatility_60, 0)",
        "multifractal_spectrum_width": "abs(coalesce(volatility_60, 0) - coalesce(rolling_volatility, 0))",
        "intermittency_proxy": "fourth_moment_20 / nullif(pow(second_moment_20, 2), 0)",
        "scaling_exponents": "ln(nullif(rolling_volatility, 0) / nullif(volatility_60, 0)) / ln(20.0 / 60.0)",
        "rolling_market_inefficiency_index": "abs(momentum) / nullif(rolling_volatility, 0)",
        "multifractal_volatility_proxy": "abs(log_returns) * abs(coalesce(volatility_60, 0) - coalesce(rolling_volatility, 0))",
        "var_oriented_multifractal_features": "abs(var_95) * coalesce(volatility_60 / nullif(rolling_volatility, 0), 1.0)",
    }
    return [
        _feature_select("price_enriched", "multifractal", version, name, expression)
        for name, expression in expressions.items()
    ]


def _risk_selects(version: str) -> list[str]:
    expressions = {
        "var": "var_95",
        "cvar": "cvar_95",
        "max_drawdown": "max_drawdown",
        "expected_drawdown": "expected_drawdown",
        "rolling_beta": "rolling_beta",
        "correlation": "correlation",
        "covariance": "covariance",
        "tail_risk": "tail_risk",
        "liquidity_risk": "liquidity_risk",
        "concentration_risk": "1.0",
        "regime_conditional_risk": "rolling_volatility * (1.0 + volatility_regime)",
    }
    return [
        _feature_select("risk_enriched", "risk", version, name, expression)
        for name, expression in expressions.items()
    ]


def _portfolio_selects(version: str) -> list[str]:
    expressions = {
        "mean_variance_baseline": "returns / nullif(pow(rolling_volatility, 2), 0)",
        "risk_parity_baseline": "1.0 / nullif(rolling_volatility, 0)",
        "hierarchical_risk_parity_optional": "cast(NULL as DOUBLE)",
        "max_weight_constraints": "0.10",
        "turnover_constraints": "abs(returns - lag(returns) over (partition by symbol, timeframe order by ts))",
        "transaction_cost_model": "0.001 * abs(returns - lag(returns) over (partition by symbol, timeframe order by ts))",
        "long_only_first": "greatest(0.0, least(0.10, returns))",
        "long_short_optional": "greatest(-0.10, least(0.10, returns))",
    }
    return [
        _feature_select("price_enriched", "portfolio", version, name, expression)
        for name, expression in expressions.items()
    ]


def _regime_selects(version: str) -> list[str]:
    expressions = {
        "volatility_regime": "volatility_regime",
        "trend_regime": "trend_regime",
        "correlation_regime": "correlation_regime",
        "liquidity_regime": "liquidity_regime",
        "multifractal_inefficiency_regime": "case when abs(momentum) / nullif(rolling_volatility, 0) > 1.0 then 1.0 else 0.0 end",
        "hidden_state_optional": "cast(NULL as DOUBLE)",
    }
    return [
        _feature_select("risk_enriched", "regime", version, name, expression)
        for name, expression in expressions.items()
    ]


def _knowledge_graph_selects(version: str) -> list[str]:
    return [
        _feature_select("bars", "knowledge_graph", version, name, "0.0")
        for name in (
            "company_entity_relation",
            "sector_relation",
            "supply_chain_relation_optional",
            "news_event_relation_optional",
            "graph_embeddings_placeholder",
        )
    ]


FEATURE_SELECTS = {
    "price_volume": _price_volume_selects,
    "lob": _lob_selects,
    "multifractal": _multifractal_selects,
    "risk": _risk_selects,
    "portfolio": _portfolio_selects,
    "regime": _regime_selects,
    "knowledge_graph": _knowledge_graph_selects,
}


def _validate_groups(groups: Sequence[str]) -> tuple[str, ...]:
    selected = tuple(groups or DEFAULT_FEATURE_GROUPS)
    invalid = sorted(set(selected) - set(FEATURE_GROUPS))
    if invalid:
        raise ValueError(
            f"Invalid feature groups {invalid!r}; expected one of {sorted(FEATURE_GROUPS)!r}"
        )
    return selected
