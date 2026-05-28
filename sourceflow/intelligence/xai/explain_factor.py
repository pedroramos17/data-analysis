"""Plain-English explanations for symbolic factors."""

from __future__ import annotations

from dataclasses import dataclass

EXPLANATIONS = {
    "coverage_intensity": (
        "Compares coverage by one source against peer coverage for the same event."
    ),
    "provider_amplification": (
        "Measures whether a provider contributes an outsized share of event coverage."
    ),
    "owner_amplification": (
        "Measures whether an owner contributes an outsized share of event coverage."
    ),
    "omission_pressure": (
        "Highlights where peer sources cover more of an event than the selected source."
    ),
    "entity_omission": (
        "Highlights entities present in peer event coverage but sparse for a source."
    ),
    "framing_divergence": (
        "Compares source framing with the event-wide framing distribution."
    ),
    "claim_conflict": (
        "Summarizes provider disagreement and contradiction edges for a claim."
    ),
    "event_conflict_risk": (
        "Combines claim conflict, source spread, and frame entropy for an event."
    ),
    "amplified_conflict_risk": (
        "Combines event conflict risk with provider amplification and "
        "frame concentration."
    ),
}


@dataclass(frozen=True, slots=True)
class FactorScoreExplanation:
    """Plain-English explanation for one factor score.

    Example:
        `explanation = explain_factor_score("coverage", "coverage", 0.8)`
    """

    factor_name: str
    expression_text: str
    score: float
    operands: dict[str, float]
    dependencies: tuple[str, ...]
    summary: str
    warnings: tuple[str, ...]


def explain_factor(factor_name: str) -> str:
    """Return a plain-English factor explanation.

    Example:
        `text = explain_factor("coverage_intensity")`
    """
    fallback = (
        f"{factor_name} is an interpretable comparison factor over source "
        "intelligence metadata."
    )
    return EXPLANATIONS.get(factor_name, fallback)


def explain_factor_score(
    factor_name: str,
    expression_text: str,
    score: float,
    operands: dict[str, float] | None = None,
    dependencies: tuple[str, ...] = (),
    percentile: float | None = None,
) -> FactorScoreExplanation:
    """Explain a factor score without making truth judgments.

    Example:
        `explain_factor_score("risk", "a*b", 0.91, {"a": .9})`
    """
    active_operands = operands or {}
    summary = _summary(factor_name, score, active_operands, percentile)
    warnings = _warnings(active_operands)
    return FactorScoreExplanation(
        factor_name,
        expression_text,
        score,
        active_operands,
        dependencies,
        summary,
        warnings,
    )


def _summary(
    factor_name: str,
    score: float,
    operands: dict[str, float],
    percentile: float | None,
) -> str:
    drivers = _driver_text(operands)
    percentile_text = _percentile_text(percentile)
    return (
        f"{factor_name} is {score:.3f}{percentile_text}. {drivers} "
        "This indicates a comparison or propagation pattern such as coverage "
        "asymmetry, provider concentration, framing divergence, evidence "
        "density, or claim disagreement. This does not mean the amplified "
        "claims are true or false."
    )


def _driver_text(operands: dict[str, float]) -> str:
    if not operands:
        return "No operand decomposition was available."
    top = sorted(operands.items(), key=lambda item: abs(item[1]), reverse=True)[:3]
    parts = [f"{name}={value:.3f}" for name, value in top]
    return "Top operand values: " + ", ".join(parts) + "."


def _percentile_text(percentile: float | None) -> str:
    if percentile is None:
        return ""
    return f" and sits near percentile {percentile:.1f}"


def _warnings(operands: dict[str, float]) -> tuple[str, ...]:
    if operands:
        return ()
    return ("Low decomposition detail; inspect source rows before escalation.",)
