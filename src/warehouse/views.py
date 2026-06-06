"""DuckDB analytical views for Quant MVP Parquet datasets."""

from __future__ import annotations

from collections.abc import Mapping, Sequence

from src.warehouse.duckdb_context import ColumnSpec, DuckDBWarehouseContext


def register_warehouse_views(
    context: DuckDBWarehouseContext,
    dataset_globs: Mapping[str, Sequence[str]] | None = None,
) -> None:
    """Register canonical base and derived warehouse views."""
    globs = dict(dataset_globs or {})
    context.create_parquet_view(
        "_w_market_bars",
        globs.get("market_bars", []),
        MARKET_BAR_COLUMNS,
    )
    context.create_parquet_view(
        "_w_features",
        globs.get("features", []),
        FEATURE_COLUMNS,
    )
    context.create_parquet_view(
        "_w_lob_features",
        globs.get("lob_features", []),
        LOB_COLUMNS,
    )
    context.create_parquet_view(
        "_w_predictions",
        globs.get("predictions", []),
        PREDICTION_COLUMNS,
    )
    context.create_parquet_view(
        "_w_portfolio_weights",
        globs.get("portfolio_weights", []),
        PORTFOLIO_WEIGHT_COLUMNS,
    )
    context.create_parquet_view(
        "_w_backtests",
        globs.get("backtests", []),
        BACKTEST_COLUMNS,
    )
    context.create_parquet_view("_w_risk", globs.get("risk", []), RISK_COLUMNS)
    for sql in DERIVED_VIEW_SQL:
        context.execute(sql)


MARKET_BAR_COLUMNS = (
    ColumnSpec("symbol", "VARCHAR", ("symbol", "asset_symbol", "ticker"), "''"),
    ColumnSpec("asset_type", "VARCHAR", ("asset_type", "asset_class"), "''"),
    ColumnSpec("exchange", "VARCHAR", ("exchange", "venue"), "''"),
    ColumnSpec("ts", "TIMESTAMP", ("ts", "timestamp", "datetime", "date")),
    ColumnSpec("timeframe", "VARCHAR", ("timeframe", "frequency", "bar_size"), "''"),
    ColumnSpec("open", "DOUBLE", ("open", "open_price")),
    ColumnSpec("high", "DOUBLE", ("high", "high_price")),
    ColumnSpec("low", "DOUBLE", ("low", "low_price")),
    ColumnSpec("close", "DOUBLE", ("close", "close_price", "adjusted_close")),
    ColumnSpec("volume", "DOUBLE", ("volume", "size")),
    ColumnSpec("provider", "VARCHAR", ("provider",), "''"),
    ColumnSpec("source", "VARCHAR", ("source", "provider"), "''"),
    ColumnSpec("ingestion_run_id", "VARCHAR", ("ingestion_run_id", "run_id"), "''"),
)

FEATURE_COLUMNS = (
    ColumnSpec("symbol", "VARCHAR", ("symbol", "asset_symbol", "ticker"), "''"),
    ColumnSpec("asset_type", "VARCHAR", ("asset_type", "asset_class"), "''"),
    ColumnSpec("ts", "TIMESTAMP", ("ts", "timestamp", "datetime", "date")),
    ColumnSpec("timeframe", "VARCHAR", ("timeframe", "frequency"), "''"),
    ColumnSpec("feature_set", "VARCHAR", ("feature_set", "feature_set_name"), "''"),
    ColumnSpec("version", "VARCHAR", ("version", "feature_version"), "''"),
    ColumnSpec("feature_name", "VARCHAR", ("feature_name", "name"), "''"),
    ColumnSpec("feature_value", "DOUBLE", ("feature_value", "value")),
    ColumnSpec("values_json", "VARCHAR", ("values_json", "features_json"), "'{}'"),
    ColumnSpec("source", "VARCHAR", ("source", "provider"), "''"),
)

LOB_COLUMNS = (
    ColumnSpec("symbol", "VARCHAR", ("symbol", "asset_symbol", "ticker"), "''"),
    ColumnSpec("asset_type", "VARCHAR", ("asset_type", "asset_class"), "''"),
    ColumnSpec("ts", "TIMESTAMP", ("ts", "timestamp", "datetime", "date")),
    ColumnSpec("timeframe", "VARCHAR", ("timeframe", "frequency"), "''"),
    ColumnSpec("bid_levels_json", "VARCHAR", ("bid_levels_json", "bids_json"), "'[]'"),
    ColumnSpec("ask_levels_json", "VARCHAR", ("ask_levels_json", "asks_json"), "'[]'"),
    ColumnSpec("spread", "DOUBLE", ("spread", "bid_ask_spread")),
    ColumnSpec("imbalance", "DOUBLE", ("imbalance", "order_book_imbalance")),
    ColumnSpec("bid_depth", "DOUBLE", ("bid_depth",)),
    ColumnSpec("ask_depth", "DOUBLE", ("ask_depth",)),
    ColumnSpec("source", "VARCHAR", ("source", "provider"), "''"),
)

PREDICTION_COLUMNS = (
    ColumnSpec("symbol", "VARCHAR", ("symbol", "asset_symbol", "ticker"), "''"),
    ColumnSpec("asset_type", "VARCHAR", ("asset_type", "asset_class"), "''"),
    ColumnSpec("ts", "TIMESTAMP", ("ts", "timestamp", "datetime", "date")),
    ColumnSpec("timeframe", "VARCHAR", ("timeframe", "frequency"), "''"),
    ColumnSpec("model_name", "VARCHAR", ("model_name", "model"), "''"),
    ColumnSpec("model_version", "VARCHAR", ("model_version", "version"), "''"),
    ColumnSpec("horizon", "VARCHAR", ("horizon", "prediction_horizon"), "''"),
    ColumnSpec("prediction", "DOUBLE", ("prediction", "pred", "score")),
    ColumnSpec("signal", "DOUBLE", ("signal", "prediction", "pred", "score")),
    ColumnSpec("confidence", "DOUBLE", ("confidence", "probability")),
    ColumnSpec(
        "explanation_json",
        "VARCHAR",
        ("explanation_json", "metadata_json"),
        "'{}'",
    ),
    ColumnSpec("source", "VARCHAR", ("source", "provider"), "''"),
)

PORTFOLIO_WEIGHT_COLUMNS = (
    ColumnSpec("symbol", "VARCHAR", ("symbol", "asset_symbol", "ticker"), "''"),
    ColumnSpec("asset_type", "VARCHAR", ("asset_type", "asset_class"), "''"),
    ColumnSpec("ts", "TIMESTAMP", ("ts", "timestamp", "datetime", "date")),
    ColumnSpec("timeframe", "VARCHAR", ("timeframe", "frequency"), "''"),
    ColumnSpec("backtest_id", "VARCHAR", ("backtest_id", "run_id"), "''"),
    ColumnSpec("portfolio_name", "VARCHAR", ("portfolio_name", "portfolio"), "''"),
    ColumnSpec("weight", "DOUBLE", ("weight", "target_weight")),
    ColumnSpec("target_weight", "DOUBLE", ("target_weight", "weight")),
    ColumnSpec("realized_weight", "DOUBLE", ("realized_weight", "weight")),
)

BACKTEST_COLUMNS = (
    ColumnSpec("symbol", "VARCHAR", ("symbol", "asset_symbol", "ticker"), "''"),
    ColumnSpec("asset_type", "VARCHAR", ("asset_type", "asset_class"), "''"),
    ColumnSpec("ts", "TIMESTAMP", ("ts", "timestamp", "datetime", "date")),
    ColumnSpec("timeframe", "VARCHAR", ("timeframe", "frequency"), "''"),
    ColumnSpec("backtest_id", "VARCHAR", ("backtest_id", "run_id"), "''"),
    ColumnSpec("name", "VARCHAR", ("name", "backtest_name"), "''"),
    ColumnSpec("portfolio_name", "VARCHAR", ("portfolio_name", "portfolio"), "''"),
    ColumnSpec("weight", "DOUBLE", ("weight", "target_weight")),
    ColumnSpec("pnl", "DOUBLE", ("pnl", "return", "simple_return")),
    ColumnSpec("cumulative_pnl", "DOUBLE", ("cumulative_pnl", "equity_curve")),
    ColumnSpec("drawdown", "DOUBLE", ("drawdown",)),
    ColumnSpec("metrics_json", "VARCHAR", ("metrics_json", "metadata_json"), "'{}'"),
)

RISK_COLUMNS = (
    ColumnSpec("symbol", "VARCHAR", ("symbol", "asset_symbol", "ticker"), "''"),
    ColumnSpec("asset_type", "VARCHAR", ("asset_type", "asset_class"), "''"),
    ColumnSpec("ts", "TIMESTAMP", ("ts", "timestamp", "datetime", "date")),
    ColumnSpec("timeframe", "VARCHAR", ("timeframe", "frequency"), "''"),
    ColumnSpec("universe", "VARCHAR", ("universe",), "''"),
    ColumnSpec("risk_model", "VARCHAR", ("risk_model", "model_name"), "''"),
    ColumnSpec("volatility", "DOUBLE", ("volatility", "realized_volatility")),
    ColumnSpec("value_at_risk", "DOUBLE", ("value_at_risk", "var")),
    ColumnSpec("expected_shortfall", "DOUBLE", ("expected_shortfall", "cvar")),
    ColumnSpec("beta", "DOUBLE", ("beta",)),
    ColumnSpec("metrics_json", "VARCHAR", ("metrics_json", "metadata_json"), "'{}'"),
)

DERIVED_VIEW_SQL = (
    """
    create or replace view v_market_bars as
    select
        symbol,
        asset_type,
        exchange,
        ts,
        timeframe,
        open,
        high,
        low,
        close,
        volume,
        coalesce(nullif(source, ''), provider, '') as source,
        ingestion_run_id
    from _w_market_bars
    where symbol <> '' and ts is not null
    """,
    """
    create or replace view v_returns as
    with ordered as (
        select
            symbol,
            asset_type,
            timeframe,
            ts,
            close,
            lag(close) over (
                partition by symbol, timeframe order by ts
            ) as previous_close
        from v_market_bars
        where close is not null
    )
    select
        symbol,
        asset_type,
        timeframe,
        ts,
        close,
        previous_close,
        close / nullif(previous_close, 0) - 1.0 as simple_return,
        ln(close / nullif(previous_close, 0)) as log_return,
        abs(ln(close / nullif(previous_close, 0))) as absolute_return,
        pow(ln(close / nullif(previous_close, 0)), 2) as squared_return
    from ordered
    where previous_close is not null and previous_close <> 0 and close > 0
    """,
    """
    create or replace view v_realized_volatility as
    select
        symbol,
        asset_type,
        timeframe,
        ts,
        stddev_samp(log_return) over (
            partition by symbol, timeframe
            order by ts rows between 19 preceding and current row
        ) as realized_volatility_20,
        stddev_samp(log_return) over (
            partition by symbol, timeframe
            order by ts rows between 59 preceding and current row
        ) as realized_volatility_60
    from v_returns
    """,
    """
    create or replace view v_multifractal_features as
    select *
    from _w_features
    where ts is not null
      and (
        lower(feature_set) like '%multifractal%'
        or lower(feature_set) like 'mf%'
        or lower(feature_name) like '%multifractal%'
        or lower(feature_name) like 'mf%'
      )
    """,
    """
    create or replace view v_lob_features as
    select
        symbol,
        asset_type,
        ts,
        timeframe,
        'lob' as feature_set,
        '' as version,
        '' as feature_name,
        cast(NULL as DOUBLE) as feature_value,
        bid_levels_json,
        ask_levels_json,
        spread,
        imbalance,
        bid_depth,
        ask_depth,
        source
    from _w_lob_features
    where ts is not null
    union all
    select
        symbol,
        asset_type,
        ts,
        timeframe,
        feature_set,
        version,
        feature_name,
        feature_value,
        '[]' as bid_levels_json,
        '[]' as ask_levels_json,
        cast(NULL as DOUBLE) as spread,
        cast(NULL as DOUBLE) as imbalance,
        cast(NULL as DOUBLE) as bid_depth,
        cast(NULL as DOUBLE) as ask_depth,
        source
    from _w_features
    where ts is not null
      and (lower(feature_set) like '%lob%' or lower(feature_name) like '%lob%')
    """,
    """
    create or replace view v_model_predictions as
    select
        symbol,
        asset_type,
        ts,
        timeframe,
        model_name,
        model_version,
        horizon,
        prediction,
        signal,
        confidence,
        explanation_json,
        source
    from _w_predictions
    where symbol <> '' and ts is not null
    """,
    """
    create or replace view v_signal_panel as
    with predictions as (
        select
            symbol,
            timeframe,
            ts,
            any_value(model_name) as model_name,
            any_value(model_version) as model_version,
            any_value(horizon) as horizon,
            max(signal) as signal,
            max(confidence) as confidence,
            any_value(explanation_json) as explanation_json
        from v_model_predictions
        group by symbol, timeframe, ts
    ),
    mf as (
        select symbol, timeframe, ts, any_value(values_json) as multifractal_json
        from v_multifractal_features
        group by symbol, timeframe, ts
    ),
    lob as (
        select
            symbol,
            timeframe,
            ts,
            max(spread) as spread,
            max(imbalance) as imbalance,
            max(bid_depth) as bid_depth,
            max(ask_depth) as ask_depth
        from v_lob_features
        group by symbol, timeframe, ts
    )
    select
        bars.symbol,
        bars.asset_type,
        bars.exchange,
        bars.ts,
        bars.timeframe,
        bars.open,
        bars.high,
        bars.low,
        bars.close,
        bars.volume,
        returns.simple_return,
        returns.log_return,
        returns.absolute_return,
        returns.squared_return,
        vol.realized_volatility_20,
        vol.realized_volatility_60,
        predictions.model_name,
        predictions.model_version,
        predictions.horizon,
        predictions.signal,
        predictions.confidence,
        predictions.explanation_json,
        mf.multifractal_json,
        lob.spread,
        lob.imbalance,
        lob.bid_depth,
        lob.ask_depth,
        bars.source
    from v_market_bars bars
    left join v_returns returns
        on returns.symbol = bars.symbol
       and returns.timeframe = bars.timeframe
       and returns.ts = bars.ts
    left join v_realized_volatility vol
        on vol.symbol = bars.symbol
       and vol.timeframe = bars.timeframe
       and vol.ts = bars.ts
    left join predictions
        on predictions.symbol = bars.symbol
       and predictions.timeframe = bars.timeframe
       and predictions.ts = bars.ts
    left join mf
        on mf.symbol = bars.symbol and mf.timeframe = bars.timeframe and mf.ts = bars.ts
    left join lob
        on lob.symbol = bars.symbol
       and lob.timeframe = bars.timeframe
       and lob.ts = bars.ts
    """,
    """
    create or replace view v_backtest_panel as
    select
        coalesce(backtests.symbol, weights.symbol, panel.symbol) as symbol,
        coalesce(
            backtests.asset_type,
            weights.asset_type,
            panel.asset_type
        ) as asset_type,
        coalesce(backtests.ts, weights.ts, panel.ts) as ts,
        coalesce(backtests.timeframe, weights.timeframe, panel.timeframe) as timeframe,
        coalesce(backtests.backtest_id, weights.backtest_id) as backtest_id,
        coalesce(backtests.name, weights.portfolio_name) as name,
        coalesce(backtests.portfolio_name, weights.portfolio_name) as portfolio_name,
        coalesce(backtests.weight, weights.weight) as weight,
        weights.target_weight,
        weights.realized_weight,
        backtests.pnl,
        backtests.cumulative_pnl,
        backtests.drawdown,
        backtests.metrics_json,
        panel.close,
        panel.simple_return,
        panel.signal,
        panel.confidence
    from _w_backtests backtests
    full outer join _w_portfolio_weights weights
        on weights.symbol = backtests.symbol
       and weights.timeframe = backtests.timeframe
       and weights.ts = backtests.ts
       and weights.backtest_id = backtests.backtest_id
    left join v_signal_panel panel
        on panel.symbol = coalesce(backtests.symbol, weights.symbol)
       and panel.timeframe = coalesce(backtests.timeframe, weights.timeframe)
       and panel.ts = coalesce(backtests.ts, weights.ts)
    where coalesce(backtests.ts, weights.ts, panel.ts) is not null
    """,
    """
    create or replace view v_risk_panel as
    select
        coalesce(risk.symbol, vol.symbol) as symbol,
        coalesce(risk.asset_type, vol.asset_type) as asset_type,
        coalesce(risk.ts, vol.ts) as ts,
        coalesce(risk.timeframe, vol.timeframe) as timeframe,
        risk.universe,
        risk.risk_model,
        coalesce(risk.volatility, vol.realized_volatility_20) as volatility,
        vol.realized_volatility_20,
        vol.realized_volatility_60,
        risk.value_at_risk,
        risk.expected_shortfall,
        risk.beta,
        risk.metrics_json
    from _w_risk risk
    full outer join v_realized_volatility vol
        on vol.symbol = risk.symbol
       and vol.timeframe = risk.timeframe
       and vol.ts = risk.ts
    where coalesce(risk.ts, vol.ts) is not null
    """,
)
