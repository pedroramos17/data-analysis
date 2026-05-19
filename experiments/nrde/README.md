# NRDE Smoke Experiment

This folder is external to the Django core. It tests a tiny path model with
optional PyTorch. If neural differential equation libraries are unavailable,
the script uses a temporal MLP-style fallback metric.

```bash
python experiments/nrde/train_smoke.py --config experiments/nrde/config.example.json
```

