"""Stress testing persistence services."""

from __future__ import annotations

from collections.abc import Mapping, Sequence

from quant4.services.registry import stable_config_hash
from quant4.services.risk.scenario_engine import run_scenarios
from sourceflow.config.feature_flags import require_feature


def build_stress_report(
    name: str,
    returns: Sequence[float],
    scenarios: Sequence[str] | None = None,
    provenance: Mapping[str, object] | None = None,
) -> object:
    """Persist an explainability report with stress scenario outputs.

    Example:
        `build_stress_report("stress", [0.01], ["2008"])`
    """
    require_feature("QUANT4_RISK_CORE")
    from quant4.models import ExplainabilityReport

    config = {"report": "stress_testing", "scenarios": list(scenarios or [])}
    return ExplainabilityReport.objects.create(
        name=name,
        component_name="stress_testing",
        config_json=config,
        config_hash=stable_config_hash(config),
        report_json=_stress_report_json(returns, scenarios),
        provenance_json=dict(provenance or {}),
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
