"""Agentic quant reasoning boundary."""

from sourceflow.quant.alpha_hypotheses import AlphaCandidate
from sourceflow.quant.event_alpha import generate_event_alpha_candidates
from sourceflow.quant.features import FeatureMatrix, build_feature_matrix, rolling_change
from sourceflow.quant.portfolio_explain import (
    PortfolioExplanation,
    PortfolioRiskContribution,
    explain_portfolio_risk,
)
from sourceflow.quant.regime_detector import (
    REGIME_STATES,
    RegimeDetectionResult,
    RegimeDetector,
    RuleBasedRegimeDetector,
)
from sourceflow.quant.risk_graph import (
    RISK_TYPES,
    PortfolioRiskAggregate,
    RiskGraph,
    RiskRule,
    RiskSignal,
    load_risk_rules,
)

__all__ = [
    "REGIME_STATES",
    "RISK_TYPES",
    "AlphaCandidate",
    "FeatureMatrix",
    "PortfolioExplanation",
    "PortfolioRiskAggregate",
    "PortfolioRiskContribution",
    "RegimeDetectionResult",
    "RegimeDetector",
    "RiskGraph",
    "RiskRule",
    "RiskSignal",
    "RuleBasedRegimeDetector",
    "build_feature_matrix",
    "explain_portfolio_risk",
    "generate_event_alpha_candidates",
    "load_risk_rules",
    "rolling_change",
]
