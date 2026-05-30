# QuantSpace Factor Lab

The factor lab converts extracted paper methodology into local symbolic factor
candidates.

Rules:

- Every `FactorCandidate.status` defaults to `NEEDS_BACKTEST`.
- Every candidate stores `support_status`.
- Generated prompts must not include profitability, live-trading, causal, or
  investment-advice claims.
- Candidates are research artifacts until Sourceflow symbolic factor mining and
  backtesting evaluate them.

The current implementation intentionally keeps generation simple and local. It
does not require paid APIs or heavy ML libraries.

## Sourceflow Adapter Boundary

`quantspace.services.sourceflow_adapter` converts a `FactorCandidate` into the
documented Sourceflow symbolic formula JSON shape without writing to Sourceflow
registry tables or claiming that the factor is valid.

The adapter currently accepts only formula trees built from:

- `rank`
- `zscore`
- `delay`
- `delta`
- `mean`
- `std`
- `corr`
- `ts_rank`
- `winsorize`
- `neutralize`
- `div_safe`
- `log1p_abs`

The returned payload preserves `NEEDS_BACKTEST`, `support_status`, and
`evidence_chunk_ids` in metadata, and sets `claims_validity` to `false`. Full
Sourceflow integration should happen only after the local Sourceflow schema and
operator registry are available and compatible.
