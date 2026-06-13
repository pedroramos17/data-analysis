"""Configurable Mamba-style state-space placeholder block."""

from __future__ import annotations

from dataclasses import asdict, dataclass

from src.models.sequence._torch import torch_modules


@dataclass(frozen=True, slots=True)
class MambaBlockConfig:
    """Config for a lightweight state-space sequence block placeholder."""

    input_dim: int
    hidden_dim: int = 64
    output_dim: int = 1
    kernel_size: int = 5
    dropout: float = 0.0


@dataclass(frozen=True, slots=True)
class MambaBlock:
    """Mamba-style placeholder with causal conv and gated mixing."""

    config: MambaBlockConfig

    def architecture_metadata(self) -> dict[str, object]:
        """Return placeholder architecture metadata."""
        return {
            "architecture": "mamba_placeholder",
            "components": [
                "state_space_sequence_block",
                "causal_convolution",
                "gated_mixing",
                "feature_projection",
                "prediction_head",
            ],
            "config": asdict(self.config),
        }

    def build(self) -> object:
        """Build a CPU-compatible PyTorch placeholder."""
        _torch, nn = torch_modules("Mamba placeholder block")
        config = self.config

        class _MambaPlaceholder(nn.Module):
            def __init__(self) -> None:
                super().__init__()
                self.projection = nn.Linear(config.input_dim, config.hidden_dim)
                self.causal_conv = nn.Conv1d(
                    config.hidden_dim,
                    config.hidden_dim,
                    config.kernel_size,
                    padding=config.kernel_size - 1,
                    groups=1,
                )
                self.gate = nn.Linear(config.hidden_dim, config.hidden_dim)
                self.mix = nn.Linear(config.hidden_dim, config.hidden_dim)
                self.dropout = nn.Dropout(config.dropout)
                self.head = nn.Linear(config.hidden_dim, config.output_dim)

            def forward(self, x: object) -> object:
                projected = self.projection(x)
                convolved = self.causal_conv(projected.transpose(1, 2)).transpose(1, 2)
                convolved = convolved[:, : projected.shape[1], :]
                gated = self.mix(convolved) * self.gate(projected).sigmoid()
                pooled = self.dropout(gated).mean(dim=1)
                return self.head(pooled)

        return _MambaPlaceholder()
