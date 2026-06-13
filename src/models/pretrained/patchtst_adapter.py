"""PatchTST adapter with local-checkpoint fallback."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Self

from src.models.pretrained.timeseries_foundation import TimeseriesFoundationAdapter


class PatchTSTAdapter(TimeseriesFoundationAdapter):
    """Adapter boundary for optional PatchTST forecasts."""

    @classmethod
    def from_config(cls, config: Mapping[str, object]) -> Self:
        adapter = super().from_config(config)
        adapter.model_name = str(config.get("model_name", "patchtst"))
        adapter.required_dependency = "transformers"
        return adapter
