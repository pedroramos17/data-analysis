"""Local metadata ingestion services for Quant datasets."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import date
from typing import TYPE_CHECKING

from quant.services.data_quality import validate_dataset_identity
from sourceflow.config.feature_flags import require_feature

if TYPE_CHECKING:
    from quant.models import Asset, MarketDataset


def save_market_dataset_metadata(
    name: str,
    source: str,
    frequency: str,
    asset: Asset | None = None,
    metadata: Mapping[str, object] | None = None,
    provenance: Mapping[str, object] | None = None,
    data_range: tuple[date | None, date | None] = (None, None),
) -> MarketDataset:
    """Create or update a MarketDataset metadata row.

    Example:
        `save_market_dataset_metadata("spy-daily", "local-csv", "1d")`
    """
    require_feature("QUANT_DATA_FOUNDATION")
    validate_dataset_identity(name, source, frequency)
    return _upsert_market_dataset(
        name,
        source,
        frequency,
        asset,
        metadata or {},
        provenance or {},
        data_range,
    )


def _upsert_market_dataset(
    name: str,
    source: str,
    frequency: str,
    asset: Asset | None,
    metadata: Mapping[str, object],
    provenance: Mapping[str, object],
    data_range: tuple[date | None, date | None],
) -> MarketDataset:
    from quant.models import MarketDataset

    return MarketDataset.objects.update_or_create(
        name=name,
        source=source,
        defaults={
            "asset": asset,
            "frequency": frequency,
            "data_start": data_range[0],
            "data_end": data_range[1],
            "row_count": _row_count(metadata),
            "metadata_json": dict(metadata),
            "provenance_json": dict(provenance),
        },
    )[0]


def _row_count(metadata: Mapping[str, object]) -> int:
    raw_value = metadata.get("rows") or 0
    try:
        return int(raw_value)
    except (TypeError, ValueError) as exc:
        raise ValueError(
            f"Invalid dataset rows {raw_value!r}; expected integer-compatible value"
        ) from exc
