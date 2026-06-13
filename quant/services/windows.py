"""Window artifact services for leakage-safe research splits."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import date
from typing import TYPE_CHECKING

from quant.services.registry import stable_config_hash
from sourceflow.config.feature_flags import require_feature

if TYPE_CHECKING:
    from quant.models import MarketDataset, WindowArtifact


def create_window_artifact(
    dataset: MarketDataset,
    name: str,
    split_metadata: Mapping[str, object],
    config: Mapping[str, object],
    random_seed: int,
    data_range: tuple[date | None, date | None],
    split_range: tuple[date | None, date | None],
    provenance: Mapping[str, object],
) -> WindowArtifact:
    """Persist metadata for a prepared research window artifact.

    Example:
        `create_window_artifact(dataset, "wf-1", {}, {}, 7, (None, None), ...)`
    """
    require_feature("QUANT_DATA_FOUNDATION")
    from quant.models import WindowArtifact

    return WindowArtifact.objects.create(
        dataset=dataset,
        name=name,
        config_json=dict(config),
        config_hash=stable_config_hash(config),
        random_seed=random_seed,
        data_start=data_range[0],
        data_end=data_range[1],
        split_start=split_range[0],
        split_end=split_range[1],
        split_metadata_json=dict(split_metadata),
        provenance_json=dict(provenance),
    )
