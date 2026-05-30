# Compute Profiles

The project separates safe local work from expensive GPU and cloud work. Django
prepares data, limits, manifests, and artifacts. Heavy training and large
experiments stay outside the core app.

## Profiles

### `local_cpu_low`

Use this on weak notebooks and default local installs.

- Backend preference: CPU / NumPy.
- Limits: small batches, small windows, no GPU, no cloud.
- Good for: ingestion, Parquet exports, basic feature store, returns, rolling
  stats, small MFDFA, simple signatures, light graph features.
- Avoid: Mamba/NRDE training, large MFDFA, large graph embedding.

Example:

```powershell
python manage.py inspect_compute --profile local_cpu_low
```

### `local_mx350_queue`

Use this only for MX350-class smoke tests and slow local queues.

- Backend preference: CUDA when available, CPU fallback required.
- Limits: micro-batches, small windows, `max_vram_gb` capped aggressively.
- Good for: CUDA smoke tests, micro wavelet/MFDFA/signature jobs.
- Avoid: full-history GPU pipelines, large graphs, large training.

Example:

```powershell
python manage.py inspect_compute --profile local_mx350_queue --native
```

### `local_rtx4060ti`

Use this when a strong local GPU is available.

- Backend preference: CUDA.
- Limits: larger batches and windows, still bounded.
- Good for: batched MFDFA, wavelet conv1d, batched signatures, correlation
  graph, tensor exports, model smoke training.
- Fallback: CPU remains available when CUDA is missing.

Example:

```powershell
python manage.py inspect_compute --profile local_rtx4060ti
```

### `cloud_student`

Use this for advanced work with student credits.

- Backend preference: cloud manifest.
- Limits: budget guard enabled, short runtime caps, partitioned jobs.
- Good for: advanced DTCWT, large batched MFDFA, large graph embedding, Mamba,
  NRDE, GLC/GNN experiments, small sweeps, feature backfills.
- Rule: do not execute expensive jobs without a manifest and budget guard.

Example:

```powershell
python manage.py inspect_compute --profile cloud_student
```

### `cloud_serverless_on_demand`

Use this for portable on-demand backfills and scheduled experiments.

- Backend preference: cloud manifest.
- Limits: partitioned, restartable, idempotent jobs.
- Good for: large batch feature generation, cloud training, scheduled
  experiments.

## Backend Rules

- `auto` chooses the profile preference and falls back to CPU when allowed.
- `cpu` uses NumPy.
- `cuda` uses optional PyTorch/CUDA when available.
- `cupy` uses optional CuPy when available.
- `native` uses optional ctypes kernels only when built; otherwise CPU fallback.
- `cloud_manifest` means plan a portable cloud job, not provider execution.

Advanced work goes to cloud by default unless `local_rtx4060ti` is selected
explicitly.

