"""MarketLab explainability report helpers."""

from __future__ import annotations

from datetime import date

from quant4.services.registry import stable_config_hash
from quant4.services.run_metadata import build_run_metadata_fields


def create_marketlab_report(
    name: str,
    report: dict[str, object],
    data_range: tuple[date, date],
    split_range: tuple[date, date],
    random_seed: int = 0,
) -> object:
    """Persist an explainability report through shared Quant4 models.

    Example:
        `create_marketlab_report("xai", {"claim_scope": "research"}, dr, sr)`
    """
    from quant4.models import ExplainabilityReport

    config = {"engine": "marketlab", "report": "explain"}
    return ExplainabilityReport.objects.create(
        name=name,
        component_name="marketlab_explain",
        config_json=config,
        config_hash=stable_config_hash(config),
        **build_run_metadata_fields(
            data_range,
            split_range,
            random_seed,
            {"engine": "marketlab"},
        ),
        feature_schema_json=_report_feature_schema(),
        report_json=dict(report),
        status="RESEARCH_ONLY",
    )


def _report_feature_schema() -> dict[str, object]:
    return {
        "inputs": ["model_run_id", "metrics", "limitations"],
        "claim_scope": "explainability_only",
    }
