"""End-to-end MVP training, prediction, backtest, and risk workflow."""

from __future__ import annotations

import json
import math
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path

from src.config.settings import RuntimeSettings, load_runtime_settings
from src.features.pipeline import FeaturePipelineConfig, build_feature_store
from src.models.explainability import alpha_validation_metrics
from src.models.inference.batch_predict import PredictionBatchResult, run_batch_prediction
from src.models.registry import build_default_model_registry, register_model_artifact
from src.providers.registry import build_provider_registry
from src.storage.artifact_store import DataLakeArtifactStore
from src.warehouse.duckdb_context import DuckDBWarehouseContext
from src.warehouse.materialize import MaterializationResult, build_research_panel

MVP_STEPS = (
    "ingest_sample_market_data",
    "save_raw_parquet",
    "register_ingestion_run",
    "build_research_panel",
    "build_features",
    "train_baseline_model",
    "train_optional_sequence_models",
    "save_model_artifact",
    "register_model_artifact",
    "batch_predict",
    "save_predictions_parquet",
    "store_latest_signals",
    "run_backtest",
    "run_risk_report",
    "export_report_json",
)


@dataclass(frozen=True, slots=True)
class MvpDemoConfig:
    """Config for the full MVP demo workflow."""

    run_id: str = "mvp_demo"
    symbols: tuple[str, ...] = ("SPY", "QQQ")
    asset_type: str = "equity"
    timeframe: str = "1d"
    start: str = "2024-01-01"
    periods: int = 30
    source: str = "sample"
    feature_version: str = "mvp_v1"
    model_name: str = "naive_return"
    model_version: str = "mvp_v1"
    horizon: str = "1d"
    optional_sequence_models: tuple[str, ...] = ()
    lake_root: Path | None = None
    duckdb_path: Path | None = None
    database_url: str = ""
    persist_feature_metadata: bool = True

    @classmethod
    def from_mapping(cls, config: Mapping[str, object]) -> "MvpDemoConfig":
        """Create workflow config from JSON/YAML mapping."""
        return cls(
            run_id=str(config.get("run_id", "mvp_demo")),
            symbols=tuple(_string_list(config.get("symbols", ("SPY", "QQQ")))),
            asset_type=str(config.get("asset_type", "equity")),
            timeframe=str(config.get("timeframe", "1d")),
            start=str(config.get("start", "2024-01-01")),
            periods=int(config.get("periods", 30)),
            source=str(config.get("source", "sample")),
            feature_version=str(config.get("feature_version", "mvp_v1")),
            model_name=str(config.get("model_name", "naive_return")),
            model_version=str(config.get("model_version", "mvp_v1")),
            horizon=str(config.get("horizon", "1d")),
            optional_sequence_models=tuple(
                _string_list(config.get("optional_sequence_models", ()))
            ),
            lake_root=_optional_path(config.get("lake_root")),
            duckdb_path=_optional_path(config.get("duckdb_path")),
            database_url=str(config.get("database_url", "")),
            persist_feature_metadata=_bool_value(
                config.get("persist_feature_metadata", True)
            ),
        )


@dataclass(frozen=True, slots=True)
class MvpStepResult:
    """One workflow step result."""

    name: str
    status: str
    metadata: dict[str, object] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class MvpDemoResult:
    """Full workflow result."""

    run_id: str
    status: str
    steps: tuple[MvpStepResult, ...]
    report_path: str = ""
    report_uri: str = ""

    def to_dict(self) -> dict[str, object]:
        return {
            "run_id": self.run_id,
            "status": self.status,
            "steps": [asdict(step) for step in self.steps],
            "report_path": self.report_path,
            "report_uri": self.report_uri,
        }


def run_mvp_demo(
    config: MvpDemoConfig | Mapping[str, object] | None = None,
    *,
    settings: RuntimeSettings | None = None,
) -> MvpDemoResult:
    """Run the complete local/cloud-provider MVP workflow."""
    active_config = _active_config(config)
    active_settings = settings or load_runtime_settings()
    registry = build_provider_registry(active_settings)
    lake_root = active_config.lake_root or active_settings.duckdb.data_lake_root
    duckdb_path = active_config.duckdb_path or active_settings.duckdb.database_path
    database_url = active_config.database_url or _database_url(active_settings)
    store = DataLakeArtifactStore(registry.get_storage())
    context = DuckDBWarehouseContext(duckdb_path, lake_root)
    steps: list[MvpStepResult] = []

    try:
        rows = sample_market_rows(active_config)
        steps.append(_step("ingest_sample_market_data", row_count=len(rows)))

        raw_objects = _save_raw_parquet(store, active_config, rows)
        steps.append(_step("save_raw_parquet", objects=raw_objects))

        asset_ids, ingestion_metadata = _register_ingestion(database_url, active_config, rows)
        rows_with_assets = _attach_asset_ids(rows, asset_ids)
        steps.append(_step("register_ingestion_run", **ingestion_metadata))

        panel = build_research_panel(
            active_config.symbols,
            active_config.start,
            _end_date(active_config),
            active_config.timeframe,
            context=context,
            output_path=lake_root / "gold" / f"{active_config.run_id}_panel.parquet",
        )
        steps.append(_panel_step(panel))

        features = build_feature_store(
            FeaturePipelineConfig(
                version=active_config.feature_version,
                universe=active_config.symbols,
                start=active_config.start,
                end=_end_date(active_config),
                timeframe=active_config.timeframe,
                output_path=lake_root
                / "gold"
                / "features"
                / f"version={active_config.feature_version}"
                / "feature_store.parquet",
                database_url=database_url,
                persist_metadata=active_config.persist_feature_metadata,
            ),
            context=context,
        )
        steps.append(_step("build_features", **asdict(features)))

        model, model_path = _train_baseline(active_config, rows_with_assets, lake_root)
        steps.append(_step("train_baseline_model", **model.metadata()))

        sequence_results = _train_optional_sequence_models(active_config, lake_root)
        steps.append(_step("train_optional_sequence_models", models=sequence_results))

        artifact = registry.get_model_registry().save_model(
            str(model.metadata()["model_name"]),
            active_config.model_version,
            model_path,
            model.metadata(),
        )
        steps.append(_step("save_model_artifact", artifact=artifact))

        artifact_record = _register_artifact(database_url, artifact, model.metadata())
        steps.append(_step("register_model_artifact", **artifact_record))

        prediction_result = _batch_predict(
            active_config,
            model,
            rows_with_assets,
            lake_root,
            database_url,
        )
        steps.append(_prediction_step("batch_predict", prediction_result))
        steps.append(_prediction_step("save_predictions_parquet", prediction_result))
        steps.append(_prediction_step("store_latest_signals", prediction_result))

        backtest_report = _backtest_report(active_config, rows_with_assets, prediction_result)
        backtest_record = _persist_backtest(database_url, active_config, backtest_report)
        backtest_object = store.save_backtest_report(
            active_config.run_id,
            "backtest_report.json",
            _json_bytes(backtest_report),
            source="mvp_demo",
            metadata=backtest_record,
        )
        steps.append(
            _step(
                "run_backtest",
                report_path=backtest_object.object.path,
                **backtest_report,
            )
        )

        risk_report = _risk_report(active_config, rows_with_assets)
        risk_record = _persist_risk(database_url, active_config, risk_report)
        risk_object = store.save_risk_report(
            active_config.run_id,
            "risk_report.json",
            _json_bytes(risk_report),
            source="mvp_demo",
            metadata=risk_record,
        )
        steps.append(_step("run_risk_report", report_path=risk_object.object.path, **risk_report))

        report = _combined_report(active_config, steps, backtest_report, risk_report)
        exported = store.save_log(
            "mvp_demo",
            active_config.start,
            f"{active_config.run_id}_report.json",
            _json_bytes(report),
            source="mvp_demo",
        )
        steps.append(_step("export_report_json", path=exported.path, uri=exported.uri))
        return MvpDemoResult(
            active_config.run_id,
            "COMPLETED",
            tuple(steps),
            exported.path,
            exported.uri,
        )
    finally:
        context.close()


def sample_market_rows(config: MvpDemoConfig) -> list[dict[str, object]]:
    """Create deterministic sample OHLCV rows for the MVP demo."""
    start_date = datetime.fromisoformat(config.start).replace(tzinfo=UTC)
    rows: list[dict[str, object]] = []
    for symbol_index, symbol in enumerate(config.symbols):
        base_price = 100.0 + symbol_index * 20.0
        previous_close = base_price
        for offset in range(config.periods):
            ts = start_date + timedelta(days=offset)
            drift = 0.002 * (symbol_index + 1)
            seasonal = ((offset % 5) - 2) * 0.001
            close = previous_close * (1.0 + drift + seasonal)
            open_price = previous_close
            high = max(open_price, close) * 1.003
            low = min(open_price, close) * 0.997
            volume = 1_000_000 + symbol_index * 100_000 + offset * 1_000
            log_return = math.log(close / previous_close) if previous_close else 0.0
            rows.append(
                {
                    "symbol": symbol,
                    "asset_type": config.asset_type,
                    "exchange": "",
                    "ts": ts,
                    "timeframe": config.timeframe,
                    "open": open_price,
                    "high": high,
                    "low": low,
                    "close": close,
                    "volume": float(volume),
                    "log_return": log_return,
                    "source": config.source,
                }
            )
            previous_close = close
    return rows


def _save_raw_parquet(
    store: DataLakeArtifactStore,
    config: MvpDemoConfig,
    rows: Sequence[Mapping[str, object]],
) -> list[dict[str, object]]:
    objects: list[dict[str, object]] = []
    for symbol in config.symbols:
        symbol_rows = [row for row in rows if row["symbol"] == symbol]
        data = _parquet_bytes(symbol_rows)
        saved = store.save_raw_data(
            config.source,
            config.asset_type,
            symbol,
            config.timeframe,
            config.start,
            "part-000.parquet",
            data,
            schema=_schema(symbol_rows),
            row_count=len(symbol_rows),
            source="mvp_demo",
        )
        objects.append(
            {
                "symbol": symbol,
                "path": saved.object.path,
                "uri": saved.object.uri,
                "rows": len(symbol_rows),
            }
        )
    return objects


def _register_ingestion(
    database_url: str,
    config: MvpDemoConfig,
    rows: Sequence[Mapping[str, object]],
) -> tuple[dict[str, int], dict[str, object]]:
    try:
        from sqlalchemy import create_engine, delete, insert

        from src.database.core_schema import (
            assets,
            create_core_tables,
            ingestion_runs,
            market_bars,
        )
    except ImportError as exc:
        return _fallback_asset_ids(config), {"status": "skipped", "reason": str(exc)}

    asset_ids: dict[str, int] = {}
    engine = create_engine(database_url)
    try:
        with engine.begin() as connection:
            create_core_tables(connection)
            run_result = connection.execute(
                insert(ingestion_runs).values(
                    source=config.source,
                    asset_type=config.asset_type,
                    symbol="ALL",
                    timeframe=config.timeframe,
                    start_ts=min(row["ts"] for row in rows) if rows else None,
                    end_ts=max(row["ts"] for row in rows) if rows else None,
                    status="COMPLETED",
                    rows_written=len(rows),
                    rows_deduplicated=0,
                    missing_ratio=0.0,
                    output_uri="",
                    content_hash="",
                    error_json={},
                    stats_json={"rows": len(rows), "symbols": list(config.symbols)},
                    error="",
                )
            )
            ingestion_run_id = int(run_result.inserted_primary_key[0])
            for symbol in config.symbols:
                asset_ids[symbol] = _asset_id(connection, assets, symbol, config.asset_type)
            for row in rows:
                asset_id = asset_ids[str(row["symbol"])]
                connection.execute(
                    delete(market_bars).where(
                        market_bars.c.asset_id == asset_id,
                        market_bars.c.ts == row["ts"],
                        market_bars.c.timeframe == row["timeframe"],
                        market_bars.c.source == row["source"],
                    )
                )
                connection.execute(
                    insert(market_bars).values(
                        asset_id=asset_id,
                        ts=row["ts"],
                        timeframe=row["timeframe"],
                        open=row["open"],
                        high=row["high"],
                        low=row["low"],
                        close=row["close"],
                        volume=row["volume"],
                        source=row["source"],
                        ingestion_run_id=ingestion_run_id,
                    )
                )
    finally:
        engine.dispose()
    return asset_ids, {"status": "registered", "rows": len(rows), "asset_ids": asset_ids}


def _asset_id(connection: object, assets: object, symbol: str, asset_type: str) -> int:
    from sqlalchemy import insert, select

    existing = connection.execute(
        select(assets.c.id).where(
            assets.c.symbol == symbol,
            assets.c.exchange == "",
            assets.c.asset_type == asset_type,
        )
    ).scalar_one_or_none()
    if existing is not None:
        return int(existing)
    result = connection.execute(
        insert(assets).values(
            symbol=symbol,
            exchange="",
            asset_type=asset_type,
            currency="USD",
            sector="",
            metadata_json={"source": "mvp_demo"},
        )
    )
    return int(result.inserted_primary_key[0])


def _train_baseline(
    config: MvpDemoConfig,
    rows: Sequence[Mapping[str, object]],
    lake_root: Path,
) -> tuple[object, Path]:
    model = build_default_model_registry().create(config.model_name, {})
    if hasattr(model, "model_version"):
        model.model_version = config.model_version
    model.fit(rows, {"target_column": "log_return"})
    path = lake_root / "models" / f"{config.model_name}_{config.model_version}.json"
    model.save(path)
    return model, path


def _train_optional_sequence_models(
    config: MvpDemoConfig,
    lake_root: Path,
) -> list[dict[str, object]]:
    if not config.optional_sequence_models:
        return []
    try:
        import torch
    except ImportError as exc:
        return [
            {"name": name, "status": "SKIPPED", "reason": f"torch unavailable: {exc}"}
            for name in config.optional_sequence_models
        ]
    results: list[dict[str, object]] = []
    for name in config.optional_sequence_models:
        metadata = _sequence_metadata(name)
        output = lake_root / "models" / f"{name}_{config.model_version}.json"
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(metadata, sort_keys=True, indent=2), encoding="utf-8")
        results.append({"name": name, "status": "COMPLETED", "artifact_path": str(output)})
    return results


def _sequence_metadata(name: str) -> dict[str, object]:
    if name == "fin_mamba_small":
        from src.models.sequence.fin_mamba import FinMambaBlock, FinMambaConfig

        return FinMambaBlock(FinMambaConfig(input_dim=4, hidden_dim=8)).architecture_metadata()
    if name == "samba_small":
        from src.models.sequence.samba_block import SambaBlock, SambaConfig

        return SambaBlock(SambaConfig(input_dim=4, hidden_dim=8)).architecture_metadata()
    if name == "tcn":
        from src.models.sequence.tcn import TCNBlock, TCNConfig

        return TCNBlock(TCNConfig(input_dim=4, hidden_dim=8)).architecture_metadata()
    if name == "gru_attention":
        from src.models.sequence.gru_attention import GRUAttentionBlock, GRUAttentionConfig

        return GRUAttentionBlock(GRUAttentionConfig(input_dim=4, hidden_dim=8)).architecture_metadata()
    return {"architecture": name, "status": "unknown_optional_model"}


def _register_artifact(
    database_url: str,
    artifact: Mapping[str, object],
    metadata: Mapping[str, object],
) -> dict[str, object]:
    try:
        record = register_model_artifact(
            database_url,
            str(metadata.get("model_name", "model")),
            str(artifact.get("version", metadata.get("model_version", "v1"))),
            str(artifact.get("artifact_uri", "")),
            metadata,
        )
    except Exception as exc:
        return {"status": "skipped", "reason": str(exc)}
    return {"status": "registered", "record": record}


def _batch_predict(
    config: MvpDemoConfig,
    model: object,
    rows: Sequence[Mapping[str, object]],
    lake_root: Path,
    database_url: str,
) -> PredictionBatchResult:
    latest_rows = _latest_rows(rows)
    return run_batch_prediction(
        model,
        latest_rows,
        config.horizon,
        output_path=lake_root / "predictions" / f"{config.run_id}_predictions.parquet",
        database_url=database_url,
        feature_set_version=config.feature_version,
    )


def _backtest_report(
    config: MvpDemoConfig,
    rows: Sequence[Mapping[str, object]],
    prediction_result: PredictionBatchResult,
) -> dict[str, object]:
    signals = {prediction.symbol: prediction.signal for prediction in prediction_result.predictions}
    returns = [float(row.get("log_return", 0.0)) * signals.get(str(row["symbol"]), 0.0) for row in rows]
    cumulative = sum(returns)
    drawdown = min(_cumulative_path(returns), default=0.0)
    return {
        "run_id": config.run_id,
        "strategy": "latest_signal_times_return",
        "observations": len(returns),
        "total_return": cumulative,
        "max_drawdown": drawdown,
        "alpha_validation": alpha_validation_metrics(rows, prediction_result.predictions),
    }


def _risk_report(config: MvpDemoConfig, rows: Sequence[Mapping[str, object]]) -> dict[str, object]:
    returns = sorted(float(row.get("log_return", 0.0)) for row in rows)
    if not returns:
        return {"run_id": config.run_id, "value_at_risk": 0.0, "cvar": 0.0, "max_drawdown": 0.0}
    index = max(0, int(0.05 * (len(returns) - 1)))
    var = returns[index]
    tail = [value for value in returns if value <= var]
    cvar = sum(tail) / len(tail) if tail else var
    return {
        "run_id": config.run_id,
        "value_at_risk": var,
        "cvar": cvar,
        "max_drawdown": min(_cumulative_path(returns), default=0.0),
        "volatility": _stddev(returns),
    }


def _persist_backtest(
    database_url: str,
    config: MvpDemoConfig,
    report: Mapping[str, object],
) -> dict[str, object]:
    return _insert_run_record(database_url, "backtest_runs", config.run_id, report)


def _persist_risk(
    database_url: str,
    config: MvpDemoConfig,
    report: Mapping[str, object],
) -> dict[str, object]:
    return _insert_run_record(database_url, "risk_runs", ",".join(config.symbols), report)


def _insert_run_record(
    database_url: str,
    table_name: str,
    name: str,
    report: Mapping[str, object],
) -> dict[str, object]:
    try:
        from sqlalchemy import MetaData, Table, create_engine, insert

        from src.database.core_schema import create_core_tables
    except ImportError as exc:
        return {"status": "skipped", "reason": str(exc)}
    engine = create_engine(database_url)
    try:
        with engine.begin() as connection:
            create_core_tables(connection)
            table = Table(table_name, MetaData(), autoload_with=connection)
            values = (
                {"name": name, "config_json": {}, "metrics_json": dict(report)}
                if table_name == "backtest_runs"
                else {"universe": name, "config_json": {}, "metrics_json": dict(report)}
            )
            result = connection.execute(insert(table).values(**values))
    finally:
        engine.dispose()
    return {"status": "registered", "id": int(result.inserted_primary_key[0])}


def _combined_report(
    config: MvpDemoConfig,
    steps: Sequence[MvpStepResult],
    backtest_report: Mapping[str, object],
    risk_report: Mapping[str, object],
) -> dict[str, object]:
    return {
        "run_id": config.run_id,
        "steps": [asdict(step) for step in steps],
        "backtest": dict(backtest_report),
        "risk": dict(risk_report),
    }


def _attach_asset_ids(
    rows: Sequence[Mapping[str, object]],
    asset_ids: Mapping[str, int],
) -> list[dict[str, object]]:
    return [dict(row) | {"asset_id": asset_ids[str(row["symbol"])]} for row in rows]


def _fallback_asset_ids(config: MvpDemoConfig) -> dict[str, int]:
    return {symbol: index + 1 for index, symbol in enumerate(config.symbols)}


def _latest_rows(rows: Sequence[Mapping[str, object]]) -> list[dict[str, object]]:
    latest: dict[str, Mapping[str, object]] = {}
    for row in rows:
        latest[str(row["symbol"])] = row
    return [dict(row) for row in latest.values()]


def _panel_step(panel: MaterializationResult) -> MvpStepResult:
    return _step(
        "build_research_panel",
        output_path=str(panel.output_path),
        row_count=panel.row_count,
        source_view=panel.source_view,
    )


def _prediction_step(name: str, result: PredictionBatchResult) -> MvpStepResult:
    return _step(
        name,
        predictions=len(result.predictions),
        parquet_path=str(result.parquet_path) if result.parquet_path else "",
        signal_count=result.signal_count,
    )


def _step(name: str, **metadata: object) -> MvpStepResult:
    return MvpStepResult(name, "COMPLETED", _json_safe_dict(metadata))


def _parquet_bytes(rows: Sequence[Mapping[str, object]]) -> bytes:
    try:
        import pyarrow as pa
        import pyarrow.parquet as pq
    except ImportError as exc:
        raise RuntimeError("pyarrow is required for MVP raw Parquet output") from exc
    sink = pa.BufferOutputStream()
    pq.write_table(pa.Table.from_pylist([dict(row) for row in rows]), sink)
    return sink.getvalue().to_pybytes()


def _schema(rows: Sequence[Mapping[str, object]]) -> list[dict[str, object]]:
    first = dict(rows[0]) if rows else {}
    return [{"name": key, "type": type(value).__name__} for key, value in first.items()]


def _database_url(settings: RuntimeSettings) -> str:
    from src.database.core_schema import sqlalchemy_url_from_database_settings

    return sqlalchemy_url_from_database_settings(settings.database)


def _active_config(
    config: MvpDemoConfig | Mapping[str, object] | None,
) -> MvpDemoConfig:
    if isinstance(config, MvpDemoConfig):
        return config
    return MvpDemoConfig.from_mapping(dict(config or {}))


def _end_date(config: MvpDemoConfig) -> str:
    start = datetime.fromisoformat(config.start)
    return (start + timedelta(days=max(0, config.periods - 1))).date().isoformat()


def _cumulative_path(returns: Sequence[float]) -> list[float]:
    values: list[float] = []
    total = 0.0
    peak = 0.0
    for value in returns:
        total += value
        peak = max(peak, total)
        values.append(total - peak)
    return values


def _stddev(values: Sequence[float]) -> float:
    if len(values) < 2:
        return 0.0
    mean = sum(values) / len(values)
    variance = sum((value - mean) ** 2 for value in values) / (len(values) - 1)
    return math.sqrt(variance)


def _json_bytes(payload: Mapping[str, object]) -> bytes:
    return json.dumps(payload, sort_keys=True, indent=2, default=str).encode("utf-8")


def _json_safe_dict(payload: Mapping[str, object]) -> dict[str, object]:
    return {str(key): _json_safe(value) for key, value in payload.items()}


def _json_safe(value: object) -> object:
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, Mapping):
        return _json_safe_dict(value)
    if isinstance(value, list | tuple):
        return [_json_safe(item) for item in value]
    if isinstance(value, str | int | float | bool) or value is None:
        return value
    return str(value)


def _string_list(value: object) -> list[str]:
    if value is None or value == "":
        return []
    if isinstance(value, str):
        return [item.strip() for item in value.split(",") if item.strip()]
    if isinstance(value, Sequence):
        return [str(item) for item in value]
    raise ValueError(f"Invalid list value {value!r}; expected list or comma string")


def _optional_path(value: object) -> Path | None:
    if value in (None, ""):
        return None
    return Path(str(value))


def _bool_value(value: object) -> bool:
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "yes", "on"}
