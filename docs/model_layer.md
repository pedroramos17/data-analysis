# Pre-Trained Model Layer

The model layer provides a stable forecasting interface for CPU-first baselines,
local-checkpoint pretrained adapters, optional sequence architectures, and
prediction persistence.

## Interface

All models implement `BaseForecastModel`:

- `fit(dataset, config)`
- `predict(dataset, horizon)`
- `explain(dataset, predictions)`
- `save(path)`
- `load(path)`
- `metadata()`

Prediction rows use `ForecastPrediction` and can be written to Parquet or the
compatibility `signals` table.

## Baselines

- `NaiveReturnBaseline` runs without optional dependencies or GPU.
- `RidgeReturnBaseline` is a pure-Python ridge baseline for small CPU batches.
- `OptionalBoostedBaseline("lightgbm")` and
  `OptionalBoostedBaseline("xgboost")` load optional dependencies only when fit.

## Pretrained Adapters

Adapters live in `src.models.pretrained`:

- `NeuralProphetAdapter`
- `ChronosAdapter`
- `PatchTSTAdapter`
- `TimesFMAdapter`

Adapters load local JSON checkpoints when `checkpoint_path` exists. Remote model
downloads are disabled by default. Missing checkpoints fail with a clear message
that names the optional live dependency and asks for a local artifact.

Local checkpoints can include:

```json
{
  "constant_prediction": 0.01,
  "confidence": 0.8,
  "normalizer_metadata": {"method": "identity"}
}
```

## Sequence Placeholders

Optional PyTorch sequence modules live in `src.models.sequence`:

- `TCNBlock`
- `GRUAttentionBlock`
- `MambaBlock`
- `FinMambaBlock`
- `SambaBlock`
- `SambaEncoder`
- `SambaForecastModel`

Fin-Mamba is a budget-friendly PyTorch architecture module with inputs for:

- `x_time`: `[batch, time, features]`
- optional `x_cross`: `[batch, assets, cross_features]`
- optional `regime_features`: `[batch, time, regime_features]`
- optional `graph_features`: `[batch, assets, graph_features]`

It returns:

- `predictions`: configured heads for return, volatility, drawdown risk, regime
  probability, and signal confidence
- `latent_states`: final sequence states and pooled causal state
- optional `diagnostics`: cross-asset weights/context and regime gate summaries

SAMBA is a hybrid financial sequence architecture that combines:

- local causal convolution branch
- selective state-space/Mamba-style branch
- sparse/low-rank attention branch
- gated fusion
- residual normalization
- branch contribution, feature saliency, and temporal contribution diagnostics

`SambaEncoder` can be used as a drop-in encoder, and `SambaForecastModel` is
registered as `samba` and `samba_forecast` in `build_default_model_registry()`.
The example config lives at `configs/samba.yaml`.

Fin-Mamba and SAMBA expose stable components for:

- state-space sequence block
- causal convolution
- gated mixing
- cross-asset conditioning
- regime embedding
- feature projection
- prediction head

They import PyTorch lazily and support CPU execution when PyTorch is installed.

## Registry And Persistence

`build_default_model_registry()` registers baseline, adapter, and SAMBA forecast
factories.

`register_model_artifact()` can insert model artifact metadata into the
SQLite/Postgres compatibility `model_artifacts` table when SQLAlchemy is
installed.

`run_batch_prediction()` supports:

- model inference,
- explanation metadata,
- Parquet prediction output through PyArrow,
- signal insertion into the compatibility `signals` table.

## Explainability And Diagnostics

`run_batch_prediction()` enriches every prediction and persisted signal with a
lightweight `explanation_json` envelope. The required fields are:

- `model_name`
- `model_version`
- `feature_set_version`
- `top_features`
- `horizon`
- `confidence`
- `uncertainty_proxy`
- `regime_context`
- `risk_context`
- `data_quality_flags`

Sequence-model hooks include temporal contribution summaries, feature saliency
placeholders, SAMBA branch diagnostics, and Fin-Mamba latent-state summaries.

`src.models.explainability.alpha_validation_metrics()` provides dependency-free
alpha diagnostics for MVP reports: IC, rank IC, hit ratio, turnover, drawdown,
Sharpe-like, Sortino-like, Calmar-like, Melao Index placeholder, correlation
with existing signals, and regime-conditional performance.
