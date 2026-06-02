"""Multifractal analysis entry points for LOB and microstructure series."""

from __future__ import annotations

from collections.abc import Mapping

from quant4.services.lob.parser import LOBSnapshot
from quant4.services.multifractal.core.mfdcca import run_mfdcca
from quant4.services.multifractal.core.mfdfa import run_mfdfa
from quant4.services.multifractal.core.partition import run_partition_function
from quant4.services.multifractal.core.types import MFDFAConfig
from quant4.services.multifractal.lob.features import build_lob_mf_series


def analyze_lob_multifractality(
    snapshots: list[LOBSnapshot],
    config: MFDFAConfig | None = None,
) -> dict[str, object]:
    """Run LOB-ready multifractal diagnostics over supplied book data.

    Example:
        `report = analyze_lob_multifractality(snapshots, MFDFAConfig())`
    """
    active_config = config or MFDFAConfig()
    series = build_lob_mf_series(snapshots)
    spread = run_mfdfa(series.spread, active_config)
    imbalance = run_mfdfa(series.imbalance, active_config)
    durations = run_partition_function(series.inter_event_duration, active_config)
    cross = run_mfdcca(series.bid_depth, series.ask_depth, active_config)
    return {
        "venue_depth_required": "optional_by_venue",
        "spread_mfdfa": _mfdfa_summary(spread.summary, spread.valid_scale_count),
        "imbalance_mfdfa": _mfdfa_summary(
            imbalance.summary,
            imbalance.valid_scale_count,
        ),
        "duration_partition": _method_summary(durations.method, durations.summary),
        "buy_sell_mfdcca": dict(cross.joint_metrics),
        "warnings": list(spread.warnings + imbalance.warnings + cross.warnings),
    }


def _mfdfa_summary(
    summary: Mapping[str, float | int | str | bool],
    valid_scale_count: int,
) -> dict[str, object]:
    payload = dict(summary)
    payload["valid_scale_count"] = valid_scale_count
    return payload


def _method_summary(
    method: str,
    summary: Mapping[str, float | int | str | bool],
) -> dict[str, object]:
    payload = dict(summary)
    payload["method"] = method
    return payload
