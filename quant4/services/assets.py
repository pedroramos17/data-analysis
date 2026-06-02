"""Asset registry helpers for Quant4."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import TYPE_CHECKING

from sourceflow.config.feature_flags import require_feature

if TYPE_CHECKING:
    from quant4.models import Asset


@dataclass(frozen=True, slots=True)
class AssetRegistrationSummary:
    """Summary of idempotent asset registration.

    Example:
        `summary = register_assets([{"symbol": "SPY"}])`
    """

    assets: list[Asset]
    created_count: int
    updated_count: int


def register_assets(
    payloads: Iterable[Mapping[str, object]],
    provenance: Mapping[str, object] | None = None,
) -> AssetRegistrationSummary:
    """Create or update local assets from registry payloads.

    Example:
        `register_assets([{"symbol": "AAPL", "asset_type": "equity"}])`
    """
    require_feature("QUANT4_DATA_FOUNDATION")
    assets: list[Asset] = []
    created_count = 0
    for payload in payloads:
        asset, created = _upsert_asset(payload, provenance or {})
        assets.append(asset)
        created_count += int(created)
    return AssetRegistrationSummary(assets, created_count, len(assets) - created_count)


def _upsert_asset(
    payload: Mapping[str, object],
    provenance: Mapping[str, object],
) -> tuple[Asset, bool]:
    from quant4.models import Asset

    symbol = _required_text(payload, "symbol").upper()
    asset_type = str(payload.get("asset_type") or "equity").strip().lower()
    exchange = str(payload.get("exchange") or "").strip().upper()
    defaults = _asset_defaults(payload, provenance)
    return Asset.objects.update_or_create(
        symbol=symbol,
        asset_type=asset_type,
        exchange=exchange,
        defaults=defaults,
    )


def _asset_defaults(
    payload: Mapping[str, object],
    provenance: Mapping[str, object],
) -> dict[str, object]:
    return {
        "name": str(payload.get("name") or "").strip(),
        "currency": str(payload.get("currency") or "USD").strip().upper(),
        "is_active": bool(payload.get("is_active", True)),
        "metadata_json": dict(payload.get("metadata") or {}),
        "provenance_json": dict(provenance),
    }


def _required_text(payload: Mapping[str, object], key: str) -> str:
    value = str(payload.get(key) or "").strip()
    if value:
        return value
    raise ValueError(f"Invalid asset {key} {value!r}; expected non-empty string")
