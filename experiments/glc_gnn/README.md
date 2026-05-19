# GLC/GNN Smoke Experiment

This folder is external to the Django core. It tests graph-ready datasets with
optional PyTorch Geometric. If graph libraries are unavailable, it uses aggregate
graph features with a small fallback metric.

```bash
python experiments/glc_gnn/train_smoke.py --config experiments/glc_gnn/config.example.json
```

