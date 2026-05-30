# Mamba Smoke Experiment

This folder is external to the Django core. It reads Parquet, NPZ, PT, or JSON
datasets produced by the pipeline and runs a tiny smoke training loop. If a real
Mamba package is unavailable, the script uses a minimal temporal fallback.

```bash
python experiments/mamba/train_smoke.py --config experiments/mamba/config.example.json
```

