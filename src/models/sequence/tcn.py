"""TCN baseline architecture placeholder."""

from __future__ import annotations

from dataclasses import asdict, dataclass

from src.models.sequence._torch import torch_modules


@dataclass(frozen=True, slots=True)
class TCNConfig:
    """Config for a causal temporal convolution baseline."""

    input_dim: int
    hidden_dim: int = 32
    output_dim: int = 1
    kernel_size: int = 3
    layers: int = 2
    dropout: float = 0.0


@dataclass(frozen=True, slots=True)
class TCNBlock:
    """Build a CPU-compatible PyTorch TCN when torch is installed."""

    config: TCNConfig

    def architecture_metadata(self) -> dict[str, object]:
        """Return placeholder architecture metadata."""
        return {
            "architecture": "tcn_baseline",
            "components": ["causal_convolution", "feature_projection", "head"],
            "config": asdict(self.config),
        }

    def build(self) -> object:
        """Build a small causal-convolution module."""
        _torch, nn = torch_modules("TCN baseline")
        layers: list[object] = []
        input_dim = self.config.input_dim
        for index in range(self.config.layers):
            dilation = 2**index
            padding = (self.config.kernel_size - 1) * dilation
            layers.extend(
                [
                    nn.Conv1d(
                        input_dim,
                        self.config.hidden_dim,
                        self.config.kernel_size,
                        padding=padding,
                        dilation=dilation,
                    ),
                    nn.ReLU(),
                    nn.Dropout(self.config.dropout),
                ]
            )
            input_dim = self.config.hidden_dim
        layers.extend(
            [
                nn.AdaptiveAvgPool1d(1),
                nn.Flatten(),
                nn.Linear(input_dim, self.config.output_dim),
            ]
        )
        return nn.Sequential(*layers)
