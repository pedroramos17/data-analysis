"""SQLite/Postgres feature metadata persistence helpers."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass(slots=True)
class FeatureMetadataRecord:
    """Aggregated compatibility-table feature record."""

    symbol: str
    asset_type: str
    ts: datetime
    feature_set: str
    version: str
    timeframe: str
    source: str
    values_json: dict[str, object] = field(default_factory=dict)


def feature_metadata_records(
    rows: Iterable[Mapping[str, object]],
) -> list[FeatureMetadataRecord]:
    """Aggregate long-form feature rows into compatibility-table records."""
    records: dict[tuple[str, str, datetime, str, str], FeatureMetadataRecord] = {}
    for row in rows:
        symbol = str(row.get("symbol") or "UNKNOWN")
        asset_type = str(row.get("asset_type") or "equity")
        ts = _timestamp(row.get("ts"))
        feature_set = str(row.get("feature_set") or "")
        version = str(row.get("version") or "")
        feature_name = str(row.get("feature_name") or "")
        if not feature_set or not version or not feature_name:
            continue
        key = (symbol, asset_type, ts, feature_set, version)
        record = records.setdefault(
            key,
            FeatureMetadataRecord(
                symbol=symbol,
                asset_type=asset_type,
                ts=ts,
                feature_set=feature_set,
                version=version,
                timeframe=str(row.get("timeframe") or ""),
                source=str(row.get("source") or ""),
            ),
        )
        record.values_json[feature_name] = _json_value(row.get("feature_value"))
    return list(records.values())


def persist_feature_metadata(
    database_url: str,
    rows: Iterable[Mapping[str, object]],
) -> int:
    """Persist aggregated feature rows into the compatibility `features` table."""
    from sqlalchemy import create_engine, delete, insert, select

    from src.database.core_schema import assets, create_core_tables, features

    records = feature_metadata_records(rows)
    engine = create_engine(database_url)
    try:
        with engine.begin() as connection:
            create_core_tables(connection)
            asset_ids: dict[tuple[str, str], int] = {}
            for record in records:
                asset_key = (record.symbol, record.asset_type)
                asset_id = asset_ids.get(asset_key)
                if asset_id is None:
                    asset_id = _asset_id(connection, assets, record.symbol, record.asset_type)
                    asset_ids[asset_key] = asset_id
                connection.execute(
                    delete(features).where(
                        features.c.asset_id == asset_id,
                        features.c.ts == record.ts,
                        features.c.feature_set == record.feature_set,
                        features.c.version == record.version,
                    )
                )
                connection.execute(
                    insert(features).values(
                        asset_id=asset_id,
                        ts=record.ts,
                        feature_set=record.feature_set,
                        version=record.version,
                        values_json={
                            "timeframe": record.timeframe,
                            "source": record.source,
                            "features": record.values_json,
                        },
                    )
                )
    finally:
        engine.dispose()
    return len(records)


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
            metadata_json={"source": "phase10_feature_pipeline"},
        )
    )
    return int(result.inserted_primary_key[0])


def _timestamp(value: object) -> datetime:
    if isinstance(value, datetime):
        return value
    return datetime.fromisoformat(str(value).replace("Z", "+00:00"))


def _json_value(value: object) -> Any:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return value
