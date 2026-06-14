"""Quality-gate helpers for Quant multifractal modules."""

from __future__ import annotations

from dataclasses import dataclass

from quant.services.multifractal.core.mfdfa import run_mfdfa
from quant.services.multifractal.defaults import (
    DEFAULT_DIAGNOSTIC_SEED,
    REPORT_RISK_DELTA_ALPHA,
)
from quant.services.multifractal.lob.multifractal_lob import (
    analyze_lob_multifractality,
)
from quant.services.multifractal.portfolio.multifractal_optimizer import (
    optimize_multifractal_adjusted_portfolio,
)
from quant.services.multifractal.regime.features import build_regime_feature_rows
from quant.services.multifractal.regime.multifractal_regime import (
    detect_multifractal_regimes,
)
from quant.services.multifractal.risk.multifractal_risk import (
    compute_asset_multifractal_risk,
)
from quant.services.multifractal.synthetic import (
    regime_switching_volatility,
    synthetic_lob_snapshots,
)


@dataclass(frozen=True, slots=True)
class QualityGate:
    """One local command that validates multifractal functionality.

    Example:
        `gate = QualityGate("django_check", "python manage.py check", True)`
    """

    name: str
    command: str
    required: bool

    def to_json_dict(self) -> dict[str, object]:
        """Return a JSON-safe quality-gate payload."""
        return {"name": self.name, "command": self.command, "required": self.required}


def quality_gate_matrix() -> list[QualityGate]:
    """Return the local validation command matrix.

    Example:
        `commands = [gate.command for gate in quality_gate_matrix()]`
    """
    return [
        QualityGate("django_check", _python("manage.py check"), True),
        QualityGate(
            "migrations",
            _python("manage.py makemigrations --check --dry-run"),
            True,
        ),
        QualityGate("quant_tests", _python("manage.py test quant"), True),
        QualityGate("full_tests", _python("manage.py test"), True),
        QualityGate("ruff", ".\\.venv-win\\Scripts\\ruff.exe check quant", True),
    ]


def run_integration_smoke(seed: int = DEFAULT_DIAGNOSTIC_SEED) -> dict[str, object]:
    """Run a small in-process smoke check across Phase 6-15 modules.

    Example:
        `result = run_integration_smoke(seed=7)`
    """
    returns = regime_switching_volatility(64, seed)
    mfdfa = run_mfdfa(returns)
    risk = compute_asset_multifractal_risk(
        returns,
        {"delta_alpha": REPORT_RISK_DELTA_ALPHA},
    )
    regimes = detect_multifractal_regimes(build_regime_feature_rows(returns))
    portfolio = optimize_multifractal_adjusted_portfolio(["SYNTH"], [[0.02]], {})
    lob = analyze_lob_multifractality(synthetic_lob_snapshots(48, seed))
    return {
        "mfdfa_ok": mfdfa.valid_scale_count > 0,
        "risk_ok": risk.risk_score >= 0.0,
        "regime_ok": bool(regimes.labels),
        "portfolio_ok": abs(sum(portfolio.weights.values()) - 1.0) <= 1e-6,
        "lob_ok": "spread_mfdfa" in lob,
        "claims_predictive_performance": False,
    }


def quality_gate_payload() -> dict[str, object]:
    """Return quality gates and smoke result for reporting."""
    return {
        "gates": [gate.to_json_dict() for gate in quality_gate_matrix()],
        "integration_smoke": run_integration_smoke(),
        "no_live_trading": True,
    }


def _python(arguments: str) -> str:
    return f".\\.venv-win\\Scripts\\python.exe {arguments}"
