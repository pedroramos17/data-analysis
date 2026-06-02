# Quant4 Multifractal Features

Feature generation lives under `quant4/services/multifractal/features/`.
Rows are designed for local research pipelines and downstream Quant4 artifacts.

The core feature row contains:

- generalized Hurst values and `hurst_h2`
- spectrum width fields such as `delta_alpha`, `alpha_min`, `alpha_max`,
  `alpha_peak`, and `spectrum_asymmetry`
- scaling diagnostics such as `tau_nonlinearity`,
  `scaling_quality_mean_r2`, and `config_hash`
- diagnostic ratios for shuffled, surrogate, finite-size, and extreme-value
  sensitivity checks

Rolling feature generation carries `window_start`, `window_end`, and a stable
`window_id`. Cross features use MF-DCCA outputs for aligned asset/benchmark
series.

The feature store writes matrices to Parquet and registers metadata through
Quant4 SQLite models, including the config hash for reproducibility. Generated
feature artifacts are local files and should not be staged unless the caller
explicitly asks for fixtures.

Small diagnostic defaults are named in
`quant4.services.multifractal.defaults`:

- `DEFAULT_DIAGNOSTIC_SEED = 17`
- `DIAGNOSTIC_BOOTSTRAP_COUNT = 4`
- `DIAGNOSTIC_FINITE_SIZE_SIMULATIONS = 2`
