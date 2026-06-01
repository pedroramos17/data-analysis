# Quant4 Multifractal Portfolio

Portfolio services live under `quant4/services/multifractal/portfolio/`. They
produce local research allocations and reports only. There is no execution,
broker, or live-trading path.

The optimizer supports minimum-variance and multifractal-adjusted allocation
logic. It can apply:

- long-only constraints
- budget and maximum-weight limits
- asset-class exposure limits
- graph-cluster concentration limits
- liquidity and transaction-cost diagnostics where provided

Constraint handling is strict. Caller-supplied constraints and graph clusters
are not dropped as a fallback. The only equal-weight fallback is when optimizer
scores are non-positive before constraints are applied. If a caller requests an
infeasible cluster or asset-class limit, the optimizer raises a clear error
instead of silently relaxing the input.

Portfolio reports include the active constraint values and booleans such as
`cluster_limit_ok` and `asset_class_limit_ok`. The output also keeps
`claims_factor_validity` false.
