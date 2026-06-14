"""Stress testing persistence services."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import date

from quant.services.registry import stable_config_hash
from quant.services.risk.scenario_engine import run_scenarios
from quant.services.run_metadata import build_run_metadata_fields
from sourceflow.config.feature_flags import require_feature


def build_stress_report(
    name: str,
    returns: Sequence[float],
    data_range: tuple[date, date],
    split_range: tuple[date, date],
    scenarios: Sequence[str] | None = None,
    random_seed: int = 0,
    provenance: Mapping[str, object] | None = None,
) -> object:
    """Persist an explainability report with stress scenario outputs.

    Example:
        `build_stress_report("stress", [0.01], dr, sr, ["2008"])`
    """
    require_feature("QUANT_RISK_CORE")
    from quant.models import ExplainabilityReport

    config = {"report": "stress_testing", "scenarios": list(scenarios or [])}
    return ExplainabilityReport.objects.create(
        name=name,
        component_name="stress_testing",
        config_json=config,
        config_hash=stable_config_hash(config),
        **build_run_metadata_fields(data_range, split_range, random_seed, provenance),
        feature_schema_json=_stress_feature_schema(),
        report_json=_stress_report_json(returns, scenarios),
        status="RESEARCH_ONLY",
    )


def _stress_report_json(
    returns: Sequence[float],
    scenarios: Sequence[str] | None,
) -> dict[str, object]:
    return {
        "scenarios": run_scenarios(returns, scenarios),
        "claim_scope": "research_risk_only",
    }


def _stress_feature_schema() -> dict[str, object]:
    return {
        "returns": "past_sequence_float",
        "scenarios": "named_research_scenarios",
    }
