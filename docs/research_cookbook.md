# Quant Systems Cookbook

This cookbook is the local-first runbook for the new QuantSpace, Quant4,
MarketLab, graph/topology, risk/regime, portfolio, LOB, full-experiment, and
multifractal research systems. The live preview is available locally at
`/cookbook/`.

The cookbook is informational. It does not execute commands from the browser.

## Safety Boundaries

- No paid API dependency
- No live trading
- Optional dependencies fail clearly
- No fake metrics

## Global Validation

```powershell
.\.venv-win\Scripts\ruff.exe check quant4
.\.venv-win\Scripts\python.exe manage.py check
.\.venv-win\Scripts\python.exe manage.py makemigrations --check --dry-run
.\.venv-win\Scripts\python.exe manage.py test quant4
.\.venv-win\Scripts\python.exe manage.py test
```

## QuantSpace

Purpose: Local paper ingestion, RAG, extraction, and factor-candidate research.

Routes:

- `/quantspace/papers/`
- `/quantspace/papers/upload/`
- `/quantspace/factor-lab/`

```powershell
.\.venv-win\Scripts\python.exe manage.py ingest_paper_pdf --path paper.pdf --title "Paper"
.\.venv-win\Scripts\python.exe manage.py build_paper_index --paper-id 1
.\.venv-win\Scripts\python.exe manage.py ask_paper --paper-id 1 --question "What validation is used?"
.\.venv-win\Scripts\python.exe manage.py extract_quant_methodology --paper-id 1
.\.venv-win\Scripts\python.exe manage.py generate_factor_candidates --extraction-id 1
.\.venv-win\Scripts\python.exe manage.py export_quantspace_parquet --paper-id 1
.\.venv-win\Scripts\python.exe manage.py test quantspace
```

Expected output: Paper rows, chunks, prompt previews, extractions, candidates,
and Parquet chunks. Optional PyMuPDF, embeddings, FAISS, and LLM providers
remain optional fallbacks.

## Quant4 Core

Purpose: Registry-first asset, dataset, and window metadata for research runs.

```powershell
.\.venv-win\Scripts\python.exe manage.py quant4_register_assets --symbol SPY --symbol QQQ --asset-type equity --exchange ARCA --currency USD
.\.venv-win\Scripts\python.exe manage.py quant4_ingest_prices --name spy-local --source csv --frequency 1d --symbol SPY
.\.venv-win\Scripts\python.exe manage.py quant4_prepare_windows --dataset-id 1 --name spy-window --split-json "{}" --config-json "{}"
.\.venv-win\Scripts\python.exe manage.py test quant4.tests.test_core
```

Expected output: Assets, `MarketDataset` rows, and `WindowArtifact` metadata
with provenance. Missing optional registry components raise clear dependency
errors.

## MarketLab

Purpose: Experimental Quant4 kernel for windows, shuffles, TDA, and benchmarks.

```powershell
.\.venv-win\Scripts\python.exe manage.py marketlab_prepare_windows --values-json "[1,2,3,4,5,6]"
.\.venv-win\Scripts\python.exe manage.py marketlab_validate_shuffles --values-json "[1,2,3,4]"
.\.venv-win\Scripts\python.exe manage.py marketlab_detect_regimes --values-json "[1,2,3,4]"
.\.venv-win\Scripts\python.exe manage.py marketlab_run_benchmark --predictions-json "[1,0]" --labels-json "[1,1]" --data-start 2024-01-01 --data-end 2024-01-02 --split-start 2024-01-02 --split-end 2024-01-02
.\.venv-win\Scripts\python.exe manage.py test quant4.tests.test_marketlab
```

Expected output: `WindowArtifact`, `GraphSnapshot`, `ModelRun`, and benchmark
diagnostics. IMF, topology, and optimizer extras fall back or fail clearly.

## Graphs And Topology

Purpose: Leakage-safe graph snapshots, topology filters, and hypergraph priors.

```powershell
.\.venv-win\Scripts\python.exe manage.py quant4_build_graphs --series-json "{""SPY"":[1,2,3],""QQQ"":[1,2,4]}" --window-end 2024-01-03 --builder correlation
.\.venv-win\Scripts\python.exe manage.py test quant4.tests.test_graph_lab
```

Expected output: `GraphSnapshot` rows with node, edge, and adjacency artifact
paths. PMFG, TMFG, RMT, and Sourceflow adapters are optional and gated.

## Risk And Regime

Purpose: Local risk metrics, stress outputs, and no-lookahead regime labels.

```powershell
.\.venv-win\Scripts\python.exe manage.py quant4_run_risk --returns-json "[0.01,-0.02,0.015]" --prices-json "[100,98,101]" --volumes-json "[1000,1200,1100]" --data-start 2024-01-01 --data-end 2024-01-03 --split-start 2024-01-03 --split-end 2024-01-03
.\.venv-win\Scripts\python.exe manage.py quant4_detect_regimes --returns-json "[0.01,-0.02,0.015]" --prices-json "[100,98,101]" --data-start 2024-01-01 --data-end 2024-01-03 --split-start 2024-01-03 --split-end 2024-01-03
.\.venv-win\Scripts\python.exe manage.py test quant4.tests.test_risk_regime
```

Expected output: `RiskRun` metrics, stress reports, `RegimeRun` labels, and
model-risk fields. Optional ruptures, HMM, and TDA dependencies are skipped
clearly.

## Portfolio

Purpose: Research-only allocation, constraints, costs, and portfolio run
records.

```powershell
.\.venv-win\Scripts\python.exe manage.py quant4_optimize_portfolio --symbols AAA,BBB --optimizer equal_weight --data-start 2024-01-01 --data-end 2024-01-31 --split-start 2024-01-31 --split-end 2024-01-31
.\.venv-win\Scripts\python.exe manage.py test quant4.tests.test_portfolio
```

Expected output: `PortfolioRun` rows with weights, trades, metrics, and risk
report paths. CVXPY, Riskfolio, PyPortfolioOpt, and HRP extras fail clearly.

## LOB Microstructure

Purpose: Optional venue-normalized order book features, labels, and baselines.

```powershell
.\.venv-win\Scripts\python.exe manage.py quant4_ingest_lob --input-path data\sample_lob.jsonl --output-dir data\quant4_lob --venue-type generic --horizon 1
.\.venv-win\Scripts\python.exe manage.py quant4_train_lob_model --input-path data\sample_lob.jsonl --model naive_imbalance --data-start 2024-01-01 --data-end 2024-01-02 --split-start 2024-01-02 --split-end 2024-01-02
.\.venv-win\Scripts\python.exe manage.py test quant4.tests.test_lob_lab
```

Expected output: `LOBRun` rows, normalized feature artifacts, labels, and
baseline metrics. PyTorch DeepLOB and TCN-LOB models remain optional stubs.

## Full Experiment

Purpose: Safe DAG orchestration from data through explainability.

```powershell
.\.venv-win\Scripts\python.exe manage.py quant4_run_full_experiment --name "global_macro_quant4_v1" --asset-classes stocks,commodities,indices,forex,futures --symbols SPY,QQQ,DIA,^DJI,^KS11,EURUSD,USDJPY,ES,NQ,CL,GC --timeframes 1d,1h,1m --horizon 1 --windows walk_forward --regimes volatility,drawdown,tda,rqa,mst,lob --graphs correlation,mst,pmfg,leadlag_signature,imf_coherence,dynamic_sparse,hypergraph --risk-models shrinkage,pca_factor,cvar,liquidity,lob --models naive,ridge,tcn,gcn_gru --portfolio-optimizers equal_weight,min_var,hrp,cvar --backtest true --no-live-trading --dry-run
.\.venv-win\Scripts\python.exe manage.py test quant4.tests.test_full_experiment
```

Expected output: Dry-run DAG output, `Experiment` status, skipped steps, and
artifact paths. Missing data and optional dependencies produce skipped steps,
not fake output.

## Multifractal

Purpose: MF-DFA, diagnostics, features, risk, regimes, portfolio, reports, and
plots.

```powershell
.\.venv-win\Scripts\python.exe manage.py quant4_import_bars --csv .\bars.csv --symbol SPY --output-root data\mf_bars
.\.venv-win\Scripts\python.exe manage.py quant4_compute_returns --bars-root data\mf_bars --output-root data\mf_returns
.\.venv-win\Scripts\python.exe manage.py quant4_mfdfa --series "0.01,-0.02,0.015,-0.005"
.\.venv-win\Scripts\python.exe manage.py quant4_mf_diagnostics --series "0.01,-0.02,0.015,-0.005"
.\.venv-win\Scripts\python.exe manage.py quant4_mf_features --symbol SPY --window-id w0 --series "0.01,-0.02,0.015,-0.005"
.\.venv-win\Scripts\python.exe manage.py quant4_mf_risk --series "0.01,-0.02,0.015,-0.005"
.\.venv-win\Scripts\python.exe manage.py quant4_mf_regime --series "0.01,-0.02,0.015,-0.005"
.\.venv-win\Scripts\python.exe manage.py quant4_mf_portfolio --symbols SPY,QQQ --variances "0.02,0.04"
.\.venv-win\Scripts\python.exe manage.py quant4_mf_report --symbol SPY
.\.venv-win\Scripts\python.exe manage.py test quant4.tests.test_multifractal_cli
.\.venv-win\Scripts\python.exe manage.py test quant4.tests.test_multifractal_quality_gates
```

Expected output: JSON summaries, Parquet feature data, Markdown reports, and plot
artifacts. scikit-learn, PyWavelets, and plotting dependencies remain optional.

## Next Improvements Required

Required Next:

- P0 Executable sample fixture pack. CSV, PDF, and JSONL fixtures make every
  cookbook command runnable.
- P0 Cookbook drift checks. Command examples should stay aligned with
  management command signatures.

Near-Term:

- P1 Quant4 web dashboard beyond the cookbook. Operators need run metadata
  views, artifact links, and status summaries.
- P1 Optional dependency status panel. Local users need to know which optional
  modules are available or skipped.
- P1 Artifact cleanup and reset commands. Repeatable local tests need a safe
  way to clear generated data artifacts.

Research Later:

- P2 Full-experiment execute-mode fixture coverage. The dry-run path is
  covered; execute mode needs deterministic local fixtures.
