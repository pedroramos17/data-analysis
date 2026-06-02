"""SQLite-backed registry adapter for multifractal datasets."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from datetime import date

from quant4.services.multifractal.data.contracts import BAR_SCHEMA_VERSION


def build_dataset_id(metadata: Mapping[str, object]) -> str:
    """Return a deterministic dataset id from normalized metadata.

    Example:
        `dataset_id = build_dataset_id({"symbol": "SPY", "timeframe": "1d"})`
    """
    normalized = json.dumps(metadata, sort_keys=True, default=str)
    digest = hashlib.sha256(normalized.encode("utf-8")).hexdigest()
    return f"q4mf_{digest[:24]}"


def register_multifractal_dataset(
    dataset_id: str,
    kind: str,
    artifact_root: str,
    metadata: Mapping[str, object],
    row_count: int,
    data_range: tuple[date | None, date | None] = (None, None),
) -> object:
    """Register a multifractal dataset in the shared SQLite metadata table.

    Example:
        `register_multifractal_dataset("id", "bars", "data/bars", {}, 10)`
    """
    from quant4.models import MarketDataset

    payload = _registry_payload(dataset_id, kind, artifact_root, metadata)
    return MarketDataset.objects.update_or_create(
        name=dataset_id,
        source="quant4_multifractal",
        defaults={
            "frequency": str(metadata.get("timeframe", "")),
            "data_start": data_range[0],
            "data_end": data_range[1],
            "row_count": int(row_count),
            "metadata_json": payload,
            "provenance_json": {"engine": "quant4_multifractal", "kind": kind},
        },
    )[0]


def dataset_metadata_from_bars(
    symbol: str,
    asset_class: str | None,
    timeframe: str,
    source: str,
    row_count: int,
    timestamp_range: tuple[object, object],
) -> dict[str, object]:
    """Build stable metadata for bar dataset identifiers.

    Example:
        `dataset_metadata_from_bars("SPY", "stock", "1d", "csv", 3, (a, b))`
    """
    return {
        "kind": "bars",
        "symbol": symbol,
        "asset_class": asset_class,
        "source": source,
        "timeframe": timeframe,
        "row_count": row_count,
        "timestamp_start": timestamp_range[0],
        "timestamp_end": timestamp_range[1],
        "schema_version": BAR_SCHEMA_VERSION,
    }


def _registry_payload(
    dataset_id: str,
    kind: str,
    artifact_root: str,
    metadata: Mapping[str, object],
) -> dict[str, object]:
    return {
        "dataset_id": dataset_id,
        "kind": kind,
        "artifact_root": artifact_root,
        "schema_version": str(metadata.get("schema_version", BAR_SCHEMA_VERSION)),
        "metadata": dict(metadata),
    }
