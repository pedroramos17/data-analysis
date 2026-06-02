# Quant4 Full Experiment Orchestrator

`quant4_run_full_experiment` is a safe local orchestrator for Quant4 MVP
modules. It builds a fixed DAG:

```text
Data -> Windows -> Features -> Regimes -> Risk -> Graphs -> Models -> Portfolio -> Backtest -> Explainability
```

Dry-run is the default. The command records an `Experiment` row with the planned
or executed step metadata, but it does not place orders, connect to brokers, or
enable live trading. Missing local data creates skipped steps with clear reasons.
Missing optional dependencies create skipped optional components rather than fake
results.

```bash
python manage.py quant4_run_full_experiment \
  --name "global_macro_quant4_v1" \
  --asset-classes stocks,commodities,indices,forex,futures \
  --symbols SPY,QQQ,DIA,^DJI,^KS11,EURUSD,USDJPY,ES,NQ,CL,GC \
  --timeframes 1d,1h,1m \
  --horizon 1 \
  --windows walk_forward \
  --regimes volatility,drawdown,tda,rqa,mst,lob \
  --graphs correlation,mst,pmfg,leadlag_signature,imf_coherence,dynamic_sparse,hypergraph \
  --risk-models shrinkage,pca_factor,cvar,liquidity,lob \
  --models naive,ridge,tcn,gcn_gru \
  --portfolio-optimizers equal_weight,min_var,hrp,cvar \
  --backtest true \
  --no-live-trading \
  --dry-run
```

Use `--execute` only for local orchestration against available artifacts. Even in
execute mode the orchestrator records skipped steps when upstream data or
optional dependencies are missing. It records artifact paths only when a step
actually finds or writes local artifacts; it does not synthesize performance
metrics to make an experiment appear complete.

`--compute-profile` defaults to `local_cpu` and is stored in the experiment
provenance for reproducibility.
