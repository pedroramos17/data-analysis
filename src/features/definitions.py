"""Feature catalog for the cheap cloud-ready quant feature pipeline."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class FeatureSpec:
    """One feature emitted by the long-form feature store."""

    group: str
    name: str
    description: str


FEATURE_GROUPS: dict[str, tuple[FeatureSpec, ...]] = {
    "price_volume": (
        FeatureSpec("price_volume", "returns", "Simple close-to-close return."),
        FeatureSpec("price_volume", "log_returns", "Log close-to-close return."),
        FeatureSpec("price_volume", "rolling_volatility", "Rolling log-return volatility."),
        FeatureSpec("price_volume", "realized_volatility", "Rolling realized volatility proxy."),
        FeatureSpec("price_volume", "momentum", "Medium-horizon close momentum."),
        FeatureSpec("price_volume", "mean_reversion", "Deviation from rolling mean close."),
        FeatureSpec("price_volume", "drawdown", "Close versus rolling peak."),
        FeatureSpec("price_volume", "liquidity_proxy", "Volume scaled by absolute return."),
        FeatureSpec("price_volume", "volume_imbalance", "Volume versus rolling average volume."),
    ),
    "lob": (
        FeatureSpec("lob", "spread", "Best-quote or provided bid/ask spread."),
        FeatureSpec("lob", "mid_price", "Mid price when quote columns exist."),
        FeatureSpec("lob", "microprice", "Microprice using best quote sizes when available."),
        FeatureSpec("lob", "order_imbalance", "Order-book imbalance."),
        FeatureSpec("lob", "depth_imbalance", "Bid/ask depth imbalance."),
        FeatureSpec("lob", "slope", "Spread scaled by displayed depth."),
        FeatureSpec("lob", "queue_pressure", "Imbalance scaled by displayed depth."),
        FeatureSpec("lob", "short_horizon_realized_volatility", "Short rolling spread volatility."),
    ),
    "multifractal": (
        FeatureSpec("multifractal", "generalized_hurst_exponent", "Rolling H(q) proxy."),
        FeatureSpec("multifractal", "mf_dfa_features", "MF-DFA fluctuation proxy."),
        FeatureSpec("multifractal", "multifractal_spectrum_width", "Volatility scale spread proxy."),
        FeatureSpec("multifractal", "intermittency_proxy", "Fourth-moment intermittency proxy."),
        FeatureSpec("multifractal", "scaling_exponents", "Rolling scaling exponent proxy."),
        FeatureSpec("multifractal", "rolling_market_inefficiency_index", "Trend-to-noise inefficiency proxy."),
        FeatureSpec("multifractal", "multifractal_volatility_proxy", "Return times spectrum width."),
        FeatureSpec("multifractal", "var_oriented_multifractal_features", "VaR-oriented tail scaling proxy."),
    ),
    "risk": (
        FeatureSpec("risk", "var", "Rolling 95% value-at-risk proxy."),
        FeatureSpec("risk", "cvar", "Rolling expected shortfall proxy."),
        FeatureSpec("risk", "max_drawdown", "Rolling maximum drawdown."),
        FeatureSpec("risk", "expected_drawdown", "Rolling expected drawdown."),
        FeatureSpec("risk", "rolling_beta", "Rolling beta to universe average return."),
        FeatureSpec("risk", "correlation", "Rolling correlation to universe average return."),
        FeatureSpec("risk", "covariance", "Rolling covariance to universe average return."),
        FeatureSpec("risk", "tail_risk", "VaR/CVaR tail gap."),
        FeatureSpec("risk", "liquidity_risk", "Inverse liquidity proxy."),
        FeatureSpec("risk", "concentration_risk", "Single-name concentration placeholder."),
        FeatureSpec("risk", "regime_conditional_risk", "Risk scaled by volatility regime."),
    ),
    "portfolio": (
        FeatureSpec("portfolio", "mean_variance_baseline", "Return over variance proxy."),
        FeatureSpec("portfolio", "risk_parity_baseline", "Inverse volatility proxy."),
        FeatureSpec("portfolio", "hierarchical_risk_parity_optional", "HRP hook placeholder."),
        FeatureSpec("portfolio", "max_weight_constraints", "Configured max-weight cap."),
        FeatureSpec("portfolio", "turnover_constraints", "Rolling turnover proxy."),
        FeatureSpec("portfolio", "transaction_cost_model", "Turnover times cost proxy."),
        FeatureSpec("portfolio", "long_only_first", "Long-only clipped allocation proxy."),
        FeatureSpec("portfolio", "long_short_optional", "Optional long-short signal proxy."),
    ),
    "regime": (
        FeatureSpec("regime", "volatility_regime", "Rolling high-volatility flag."),
        FeatureSpec("regime", "trend_regime", "Momentum sign regime."),
        FeatureSpec("regime", "correlation_regime", "High-correlation flag."),
        FeatureSpec("regime", "liquidity_regime", "Low-liquidity flag."),
        FeatureSpec("regime", "multifractal_inefficiency_regime", "High inefficiency flag."),
        FeatureSpec("regime", "hidden_state_optional", "Fin-Mamba/SAMBA hidden-state hook."),
    ),
    "knowledge_graph": (
        FeatureSpec("knowledge_graph", "company_entity_relation", "Company/entity relation hook."),
        FeatureSpec("knowledge_graph", "sector_relation", "Sector relation hook."),
        FeatureSpec("knowledge_graph", "supply_chain_relation_optional", "Supply-chain relation hook."),
        FeatureSpec("knowledge_graph", "news_event_relation_optional", "News-event relation hook."),
        FeatureSpec("knowledge_graph", "graph_embeddings_placeholder", "Graph embedding hook."),
    ),
}

DEFAULT_FEATURE_GROUPS = tuple(FEATURE_GROUPS)
DEFAULT_FEATURE_VERSION = "phase10_v1"


def feature_names(group: str | None = None) -> tuple[str, ...]:
    """Return feature names for one group or the whole catalog."""
    groups = {group: FEATURE_GROUPS[group]} if group else FEATURE_GROUPS
    return tuple(spec.name for specs in groups.values() for spec in specs)
