# SAMBA

SAMBA is an optional hybrid sequence architecture registered as `samba` and
`samba_forecast` in the default forecast model registry.

## Components

- local causal convolution branch
- Mamba-style state-space branch
- low-rank attention branch
- gated branch fusion
- residual normalization
- optional cross-asset conditioning
- forecast and uncertainty heads

## Diagnostics

SAMBA exposes the Phase 14 sequence diagnostics contract:

- temporal contribution summary
- feature saliency placeholder
- branch contribution weights and summaries
- uncertainty proxy
- optional cross-asset weights

## Registry Usage

```python
from src.models.registry import build_default_model_registry

registry = build_default_model_registry()
model = registry.create("samba", {"input_dim": 4, "hidden_dim": 16})
```

Row-based prediction requires PyTorch. Metadata and config parsing work without
PyTorch so local CLI/API commands can inspect model availability safely.

## Config

See `configs/samba.yaml` for an example model configuration and documented
diagnostic fields.
