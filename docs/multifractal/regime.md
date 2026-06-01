# Quant4 Multifractal Regimes

Regime detection lives under `quant4/services/multifractal/regime/`. The first
implementation is a deterministic rule-based detector with a simple CUSUM
change-point baseline. Optional clustering or HMM detectors can be added later
behind dependency checks.

Regime feature rows are built through
`quant4.services.multifractal.regime.features.build_regime_feature_rows`.
The CLI, report builder, and quality-gate smoke tests all use this helper so
that synthetic regime examples stay consistent.

Named rule defaults live in `quant4.services.multifractal.defaults`:

- `REGIME_STRESS_DRAWDOWN_THRESHOLD = -0.15`
- `REGIME_STRESS_LIQUIDITY_THRESHOLD = 0.85`
- `REGIME_TREND_HURST_THRESHOLD = 0.58`
- `REGIME_MEAN_REVERSION_HURST_THRESHOLD = 0.42`
- `REGIME_DELTA_ALPHA_FLOOR = 0.45`
- `REGIME_VOLATILITY_FLOOR = 0.025`

Labels include calm efficient, persistent trend, anti-persistent
mean-reversion, turbulent multifractal, crash/liquidity stress, and
inconclusive. The latest label is a research diagnostic only and is not a
trading signal.
