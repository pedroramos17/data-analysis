"""MarketLab explainability report helpers."""

from __future__ import annotations

from quant4.services.registry import stable_config_hash


def create_marketlab_report(name: str, report: dict[str, object]) -> object:
    """Persist an explainability report through shared Quant4 models."""
    from quant4.models import ExplainabilityReport

    config = {"engine": "marketlab", "report": "explain"}
    return ExplainabilityReport.objects.create(
        name=name,
        component_name="marketlab_explain",
        config_json=config,
        config_hash=stable_config_hash(config),
        random_seed=0,
        feature_schema_json=_report_feature_schema(),
        report_json=dict(report),
        provenance_json={"engine": "marketlab"},
        status="RESEARCH_ONLY",
    )


def _report_feature_schema() -> dict[str, object]:
    return {
        "inputs": ["model_run_id", "metrics", "limitations"],
        "claim_scope": "explainability_only",
    }
