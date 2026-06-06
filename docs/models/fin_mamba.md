# Fin-Mamba

Fin-Mamba is an optional PyTorch sequence architecture for financial time series.
It is a CPU-safe architecture module, not a mandatory runtime dependency.

## Inputs

| Input | Shape | Purpose |
| --- | --- | --- |
| `x_time` | `[batch, time, features]` | Main causal time-series features |
| `x_cross` | `[batch, assets, features]` | Optional cross-asset context |
| `regime_features` | `[batch, time, features]` | Optional regime context |
| `graph_features` | `[batch, assets, features]` | Optional graph/relationship context |

## Components

- input projection
- causal normalization
- Mamba-style state-space placeholder
- causal depthwise convolution
- gated residual mixing
- optional regime fusion
- optional cross-asset and graph fusion
- return, volatility, drawdown, regime, and confidence heads

## Outputs

`FinMambaBlock(...).build()` returns a module that emits:

- `predictions`
- `latent_states`
- optional `diagnostics`

Diagnostics include temporal contribution summaries, feature saliency
placeholders, cross-asset weights/context, regime gate summaries, and compact
latent-state summaries.

## Usage

```python
from src.models.sequence.fin_mamba import FinMambaBlock, FinMambaConfig

model = FinMambaBlock(FinMambaConfig(input_dim=8, hidden_dim=32)).build()
```

PyTorch is imported lazily. Tests skip when PyTorch is unavailable.
