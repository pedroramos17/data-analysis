"""Modular regime detector interface and deterministic baseline."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Mapping, Protocol

from sourceflow.quant.features import FeatureMatrix, rolling_change

REGIME_STATES = (
    "low_volatility",
    "high_volatility",
    "crisis",
    "recovery",
    "liquidity_shock",
    "risk_on",
    "risk_off",
    "trend",
    "mean_reversion",
)
_CONFIDENCE_QUANTUM = Decimal("0.01")


@dataclass(frozen=True)
class RegimeDetectionResult:
    regime_probabilities: Mapping[str, Decimal]
    dominant_regime: str
    linked_belief_ids: tuple[str, ...] = ()
    explanation: str = ""
    trigger_risk_recompute: bool = False


class RegimeDetector(Protocol):
    def detect(self, matrix: FeatureMatrix, *, linked_beliefs: tuple[object, ...] = ()) -> RegimeDetectionResult:
        """Detect market regime probabilities from a feature matrix."""


class RuleBasedRegimeDetector:
    """Auditable deterministic regime detector over normalized features."""

    def detect(self, matrix: FeatureMatrix, *, linked_beliefs: tuple[object, ...] = ()) -> RegimeDetectionResult:
        latest = matrix.latest()
        volatility = latest.get("volatility", Decimal("0"))
        liquidity = latest.get("liquidity", Decimal("1"))
        return_value = latest.get("return", Decimal("0"))
        kg_risk = latest.get("kg_risk", Decimal("0"))
        trend_strength = latest.get("trend_strength", Decimal("0"))
        multifractal_stress = latest.get("multifractal_stress", Decimal("0"))
        raw = {
            "low_volatility": max(Decimal("0"), Decimal("0.35") - volatility),
            "high_volatility": max(Decimal("0"), volatility + multifractal_stress / Decimal("2")),
            "crisis": max(Decimal("0"), volatility + kg_risk - liquidity),
            "recovery": max(Decimal("0"), return_value + liquidity - kg_risk),
            "liquidity_shock": max(Decimal("0"), Decimal("1") - liquidity),
            "risk_on": max(Decimal("0"), return_value + liquidity - volatility),
            "risk_off": max(Decimal("0"), kg_risk + volatility - return_value),
            "trend": max(Decimal("0"), abs(trend_strength)),
            "mean_reversion": max(Decimal("0"), volatility - abs(trend_strength)),
        }
        probabilities = _normalize(raw)
        dominant = max(probabilities, key=probabilities.get) if probabilities else "low_volatility"
        trigger = dominant in {"high_volatility", "crisis", "liquidity_shock", "risk_off"} or rolling_change(matrix, "kg_risk") > Decimal("0.20")
        return RegimeDetectionResult(
            regime_probabilities=probabilities,
            dominant_regime=dominant,
            linked_belief_ids=tuple(str(getattr(belief, "pk", belief)) for belief in linked_beliefs),
            explanation=f"dominant regime {dominant} from volatility/liquidity/KG-risk features",
            trigger_risk_recompute=trigger,
        )


def _normalize(raw: Mapping[str, Decimal]) -> dict[str, Decimal]:
    total = sum(raw.values(), Decimal("0"))
    if total <= 0:
        return {state: (Decimal("1.00") if state == "low_volatility" else Decimal("0.00")) for state in REGIME_STATES}
    return {state: (raw[state] / total).quantize(_CONFIDENCE_QUANTUM) for state in REGIME_STATES}
