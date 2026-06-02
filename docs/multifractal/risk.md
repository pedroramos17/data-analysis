# Quant4 Multifractal Risk

Risk services live under `quant4/services/multifractal/risk/`. They separate
traditional risk, multifractal risk, stress scenarios, and report rendering.
Outputs are diagnostics, not forecasts or trading recommendations.

VaR and expected shortfall use a loss convention:

- Returns are converted to non-negative losses as `max(0.0, -return)`.
- VaR is reported as a non-negative loss value.
- Expected shortfall is the mean loss in the VaR tail.
- If the sample has no losses at the requested confidence level, VaR and
  expected shortfall return `0.0`.

Risk scores combine traditional components such as realized volatility,
drawdown, downside volatility, VaR, and expected shortfall with multifractal
components such as `delta_alpha`, intermittency, Hurst deviation, scaling
instability, finite-size warnings, and extreme-value sensitivity.

Report defaults are named in
`quant4.services.multifractal.defaults`:

- `REPORT_RISK_DELTA_ALPHA = 0.2`
- `REPORT_RISK_INTERMITTENCY = 0.2`

The report code preserves the no-prediction boundary in JSON and Markdown
payloads.
