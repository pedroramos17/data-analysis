# Quant4 Multifractal ML

ML helpers live under `quant4/services/multifractal/ml/`. They build
time-ordered supervised datasets from standard, multifractal, risk, regime,
and cross-asset features.

Dataset rules:

- Targets are horizon-aware.
- Walk-forward splits are ordered in time and can include a purge gap.
- Random train/test splits are intentionally avoided.
- Evaluation payloads keep `claims_predictive_performance` false.

Baseline models:

- `majority` is the deterministic local fallback and requires no optional
  dependencies.
- `logistic_regression`, `random_forest`, and `gradient_boosting` run real
  scikit-learn estimators when scikit-learn is installed.
- If scikit-learn is missing, those optional model names raise a clear
  dependency error and do not silently become the majority fallback.

The shared model seed is named as `DEFAULT_MODEL_RANDOM_SEED = 17` in
`quant4.services.multifractal.defaults`.
