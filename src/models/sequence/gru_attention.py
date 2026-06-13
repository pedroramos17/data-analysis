"""GRU-attention baseline architecture placeholder."""

from __future__ import annotations

from dataclasses import asdict, dataclass

from src.models.sequence._torch import torch_modules


@dataclass(frozen=True, slots=True)
class GRUAttentionConfig:
    """Config for a GRU with additive attention head."""

    input_dim: int
    hidden_dim: int = 32
    output_dim: int = 1
    layers: int = 1
    dropout: float = 0.0


@dataclass(frozen=True, slots=True)
class GRUAttentionBlock:
    """Build a GRU-attention module when torch is installed."""

    config: GRUAttentionConfig

    def architecture_metadata(self) -> dict[str, object]:
        """Return placeholder architecture metadata."""
        return {
            "architecture": "gru_attention_baseline",
            "components": ["gru_encoder", "attention_pooling", "prediction_head"],
            "config": asdict(self.config),
        }

    def build(self) -> object:
        """Build the optional PyTorch module."""
        torch, nn = torch_modules("GRU-attention baseline")
        config = self.config

        class _GRUAttention(nn.Module):
            def __init__(self) -> None:
                super().__init__()
                self.gru = nn.GRU(
                    config.input_dim,
                    config.hidden_dim,
                    config.layers,
                    batch_first=True,
                    dropout=config.dropout if config.layers > 1 else 0.0,
                )
                self.attention = nn.Linear(config.hidden_dim, 1)
                self.head = nn.Linear(config.hidden_dim, config.output_dim)

            def forward(self, x: object) -> object:
                encoded, _hidden = self.gru(x)
                weights = torch.softmax(self.attention(encoded), dim=1)
                pooled = (encoded * weights).sum(dim=1)
                return self.head(pooled)

        return _GRUAttention()
