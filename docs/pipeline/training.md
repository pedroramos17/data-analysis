# Training

Training is provider-neutral. Baselines run locally by default. Sequence models can run locally in small fallback mode or be planned for RunPod GPU execution through the compute provider.

## Baseline Command

```bash
python3 -m src.cli train run --config configs/train_baseline.yaml
```

## Optional Small Sequence Commands

```bash
python3 -m src.cli train run --config configs/train_fin_mamba_small.yaml
python3 -m src.cli train run --config configs/train_samba_small.yaml
```

## RunPod Planning Command

```bash
python3 -m src.cli compute runpod dry-run --config configs/train_gpu_runpod.yaml
```

## Real RunPod Submit

```bash
RUNPOD_DRY_RUN=false \
RUNPOD_API_KEY=... \
python3 -m src.cli compute runpod submit --config configs/train_gpu_runpod.yaml --confirm-cost
```

Real submit also requires remote object-storage URIs and budget guard approval. The default is dry-run and does not launch paid infrastructure.

## Outputs

- Model JSON or checkpoint artifacts under `data/lake/models`.
- Model cards with metrics and runtime metadata.
- Optional RunPod job manifests for GPU planning.

## Safety Rules

- All provider selection goes through `ProviderRegistry`.
- Training code stays provider-neutral and does not import RunPod SDKs.
- GPU jobs require timeout, idle timeout, cost guard, and artifact/log/metric paths.
- No live trading, broker execution, or profitability claims are part of training.
