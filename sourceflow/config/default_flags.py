"""Default feature flags for Sourceflow finance intelligence."""

from __future__ import annotations

DEFAULT_FEATURE_FLAGS: dict[str, bool] = {
    "FIN_DATA_CORE": True,
    "FIN_DATA_SEC_EDGAR": True,
    "FIN_DATA_FRED": True,
    "FIN_DATA_CFTC_COT": True,
    "FIN_DATA_YAHOO_RESEARCH": False,
    "FIN_DATA_WEB_SCRAPE_PUBLIC": False,
    "FIN_DATA_OPTIONS": False,
    "FIN_DATA_FUTURES": False,
    "FIN_DATA_COMMODITIES": False,
    "FIN_DATA_GLOBAL_MARKET_WINDOWS": True,
    "FIN_MULTIFRACTAL_CORE": True,
    "FIN_MULTIFRACTAL_WAVELET": True,
    "FIN_MULTIFRACTAL_EMD": False,
    "FIN_STATS_HM_CORRELATION": True,
    "FIN_STATS_MELAO_INDEX": True,
    "FIN_GRAPH_CORE": True,
    "FIN_MODEL_BASELINE": True,
    "FIN_MODEL_MCI_GRU": False,
    "FIN_MODEL_GNN": False,
    "FIN_MODEL_EXPERIMENTAL_TORCH": False,
    "FIN_XAI_REPORTS": True,
}
