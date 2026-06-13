"""Budget-friendly Fin-Mamba sequence architecture module."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path

from src.models.sequence._torch import torch_modules

DEFAULT_OUTPUT_TARGETS = (
    "return_forecast",
    "volatility_forecast",
    "drawdown_risk",
    "regime_probability",
    "signal_confidence",
)
ALLOWED_OUTPUT_TARGETS = frozenset(DEFAULT_OUTPUT_TARGETS)


@dataclass(frozen=True, slots=True)
class FinMambaConfig:
    """Config for a compact financial Mamba-style architecture.

    Example:
        `FinMambaConfig(input_dim=32, hidden_dim=64, horizon=5)`
    """

    input_dim: int
    hidden_dim: int = 64
    num_layers: int = 2
    dropout: float = 0.0
    horizon: int = 1
    asset_conditioning: bool = True
    use_regime_features: bool = True
    use_graph_features: bool = True
    output_targets: tuple[str, ...] = field(default_factory=lambda: DEFAULT_OUTPUT_TARGETS)
    kernel_size: int = 5
    regime_classes: int = 3

    def __post_init__(self) -> None:
        """Normalize and validate config values."""
        object.__setattr__(self, "output_targets", tuple(self.output_targets))
        _require_positive("input_dim", self.input_dim)
        _require_positive("hidden_dim", self.hidden_dim)
        _require_positive("num_layers", self.num_layers)
        _require_positive("horizon", self.horizon)
        _require_positive("kernel_size", self.kernel_size)
        _require_positive("regime_classes", self.regime_classes)
        if not 0.0 <= self.dropout < 1.0:
            raise ValueError("Invalid dropout; expected 0 <= dropout < 1")
        invalid_targets = set(self.output_targets) - ALLOWED_OUTPUT_TARGETS
        if invalid_targets:
            raise ValueError(
                f"Invalid output_targets {sorted(invalid_targets)!r}; "
                f"expected subset of {sorted(ALLOWED_OUTPUT_TARGETS)!r}"
            )


@dataclass(frozen=True, slots=True)
class FinMambaBlock:
    """Builder for a CPU-friendly Fin-Mamba PyTorch module.

    Example:
        `model = FinMambaBlock(FinMambaConfig(input_dim=8)).build()`
    """

    config: FinMambaConfig

    def architecture_metadata(self) -> dict[str, object]:
        """Return architecture metadata without importing PyTorch."""
        return {
            "architecture": "fin_mamba",
            "components": [
                "input_projection",
                "causal_normalization",
                "state_space_sequence_block",
                "causal_convolution",
                "gated_mixing",
                "gated_residual_block",
                "cross_asset_conditioning",
                "regime_embedding",
                "graph_feature_fusion",
                "feature_projection",
                "prediction_head",
                "temporal_contribution_summary",
                "feature_saliency_placeholder",
                "latent_state_summary",
            ],
            "prediction_heads": list(self.config.output_targets),
            "config": asdict(self.config),
        }

    def build(self) -> object:
        """Build the optional PyTorch Fin-Mamba module."""
        torch, nn = torch_modules("Fin-Mamba architecture")
        config = self.config

        class _CausalNormalization(nn.Module):
            """Per-step feature normalization that does not mix future timesteps."""

            def __init__(self) -> None:
                super().__init__()
                self.norm = nn.LayerNorm(config.hidden_dim)

            def forward(self, x_time: object) -> object:
                return self.norm(x_time)

        class _MambaStateSpacePlaceholder(nn.Module):
            """Small causal state-space placeholder with cumulative dynamics."""

            def __init__(self) -> None:
                super().__init__()
                self.input_gate = nn.Linear(config.hidden_dim, config.hidden_dim)
                self.state_update = nn.Linear(config.hidden_dim, config.hidden_dim)
                self.output_projection = nn.Linear(config.hidden_dim, config.hidden_dim)

            def forward(self, x_time: object) -> object:
                gate = torch.sigmoid(self.input_gate(x_time))
                update = torch.tanh(self.state_update(x_time)) * gate
                state = torch.cumsum(update, dim=1)
                return self.output_projection(torch.tanh(state))

        class _FinMambaLayer(nn.Module):
            """Causal SSM, depthwise convolution, and gated residual mixing."""

            def __init__(self) -> None:
                super().__init__()
                self.causal_norm = _CausalNormalization()
                self.state_space = _MambaStateSpacePlaceholder()
                self.depthwise_conv = nn.Conv1d(
                    config.hidden_dim,
                    config.hidden_dim,
                    config.kernel_size,
                    padding=config.kernel_size - 1,
                    groups=config.hidden_dim,
                )
                self.local_projection = nn.Linear(config.hidden_dim, config.hidden_dim)
                self.mix = nn.Linear(config.hidden_dim * 2, config.hidden_dim)
                self.gate = nn.Linear(config.hidden_dim * 2, config.hidden_dim)
                self.dropout = nn.Dropout(config.dropout)

            def forward(self, x_time: object) -> object:
                normalized = self.causal_norm(x_time)
                sequence_state = self.state_space(normalized)
                local_state = self.depthwise_conv(
                    normalized.transpose(1, 2)
                ).transpose(1, 2)
                local_state = local_state[:, : normalized.shape[1], :]
                local_state = self.local_projection(local_state)
                joined = torch.cat([sequence_state, local_state], dim=-1)
                mixed = torch.tanh(self.mix(joined))
                gate = torch.sigmoid(self.gate(joined))
                return x_time + self.dropout(mixed * gate)

        class _FinMambaModel(nn.Module):
            """Financial Mamba-style model with optional market context fusion."""

            def __init__(self) -> None:
                super().__init__()
                self.config = config
                self.input_projection = nn.Linear(config.input_dim, config.hidden_dim)
                self.input_norm = _CausalNormalization()
                self.layers = nn.ModuleList(
                    [_FinMambaLayer() for _ in range(config.num_layers)]
                )
                self.cross_projection = nn.LazyLinear(config.hidden_dim)
                self.graph_projection = nn.LazyLinear(config.hidden_dim)
                self.cross_query = nn.Linear(config.hidden_dim, config.hidden_dim)
                self.cross_key = nn.Linear(config.hidden_dim, config.hidden_dim)
                self.cross_value = nn.Linear(config.hidden_dim, config.hidden_dim)
                self.cross_fusion = nn.Linear(config.hidden_dim, config.hidden_dim)
                self.regime_projection = nn.LazyLinear(config.hidden_dim)
                self.regime_gate = nn.Linear(config.hidden_dim, config.hidden_dim)
                self.heads = nn.ModuleDict(_build_heads(config, nn))

            def forward(
                self,
                x_time: object,
                x_cross: object | None = None,
                regime_features: object | None = None,
                graph_features: object | None = None,
                return_diagnostics: bool = False,
            ) -> dict[str, object]:
                """Run a forward pass and return predictions plus latent states."""
                _validate_time_input(x_time, config)
                hidden = self.input_norm(self.input_projection(x_time))
                diagnostics: dict[str, object] = {}

                hidden = self._fuse_regime_features(
                    hidden,
                    regime_features,
                    diagnostics,
                    return_diagnostics,
                )
                for layer in self.layers:
                    hidden = layer(hidden)
                hidden = self._fuse_cross_asset_context(
                    hidden,
                    x_cross,
                    graph_features,
                    diagnostics,
                    return_diagnostics,
                )

                pooled = hidden[:, -1, :]
                if return_diagnostics:
                    diagnostics |= _sequence_diagnostics(x_time, hidden, pooled, torch)
                result: dict[str, object] = {
                    "predictions": self._predictions(pooled),
                    "latent_states": {"sequence": hidden, "pooled": pooled},
                }
                if return_diagnostics:
                    result["diagnostics"] = diagnostics
                return result

            def save_checkpoint(self, path: str | Path) -> None:
                """Save config and model state_dict to a local checkpoint."""
                checkpoint_path = Path(path)
                checkpoint_path.parent.mkdir(parents=True, exist_ok=True)
                torch.save(
                    {"config": asdict(config), "state_dict": self.state_dict()},
                    checkpoint_path,
                )

            def load_checkpoint(self, path: str | Path, strict: bool = True) -> None:
                """Load a checkpoint into an initialized model instance."""
                checkpoint = torch.load(Path(path), map_location="cpu")
                self.load_state_dict(checkpoint["state_dict"], strict=strict)

            def _fuse_regime_features(
                self,
                hidden: object,
                regime_features: object | None,
                diagnostics: dict[str, object],
                return_diagnostics: bool,
            ) -> object:
                if not config.use_regime_features or regime_features is None:
                    return hidden
                _validate_time_context("regime_features", regime_features, hidden)
                regime_hidden = self.regime_projection(regime_features)
                gate = torch.sigmoid(self.regime_gate(regime_hidden))
                if return_diagnostics:
                    diagnostics["regime_gate_mean"] = gate.mean(dim=(1, 2))
                return hidden + gate * regime_hidden

            def _fuse_cross_asset_context(
                self,
                hidden: object,
                x_cross: object | None,
                graph_features: object | None,
                diagnostics: dict[str, object],
                return_diagnostics: bool,
            ) -> object:
                tokens = self._asset_tokens(x_cross, graph_features)
                if not tokens:
                    return hidden
                asset_tokens = torch.cat(tokens, dim=1)
                query = self.cross_query(hidden[:, -1, :]).unsqueeze(-1)
                keys = self.cross_key(asset_tokens)
                values = self.cross_value(asset_tokens)
                scores = torch.matmul(keys, query).squeeze(-1) / config.hidden_dim**0.5
                weights = torch.softmax(scores, dim=1)
                context = torch.sum(values * weights.unsqueeze(-1), dim=1)
                if return_diagnostics:
                    diagnostics["cross_asset_weights"] = weights
                    diagnostics["cross_asset_context"] = context
                return hidden + self.cross_fusion(context).unsqueeze(1)

            def _asset_tokens(
                self,
                x_cross: object | None,
                graph_features: object | None,
            ) -> list[object]:
                tokens: list[object] = []
                if config.asset_conditioning and x_cross is not None:
                    _validate_asset_context("x_cross", x_cross)
                    tokens.append(self.cross_projection(x_cross))
                if config.use_graph_features and graph_features is not None:
                    _validate_asset_context("graph_features", graph_features)
                    tokens.append(self.graph_projection(graph_features))
                return tokens

            def _predictions(self, pooled: object) -> dict[str, object]:
                predictions: dict[str, object] = {}
                for target, head in self.heads.items():
                    raw = head(pooled)
                    predictions[target] = _format_prediction(raw, target, config, torch)
                return predictions

        return _FinMambaModel()


def _build_heads(config: FinMambaConfig, nn: object) -> dict[str, object]:
    heads: dict[str, object] = {}
    for target in config.output_targets:
        output_dim = config.horizon * _target_width(target, config)
        heads[target] = nn.Linear(config.hidden_dim, output_dim)
    return heads


def _target_width(target: str, config: FinMambaConfig) -> int:
    if target == "regime_probability":
        return config.regime_classes
    return 1


def _format_prediction(
    raw: object,
    target: str,
    config: FinMambaConfig,
    torch: object,
) -> object:
    if target == "regime_probability":
        values = raw.reshape(raw.shape[0], config.horizon, config.regime_classes)
        return torch.softmax(values, dim=-1)
    values = raw.reshape(raw.shape[0], config.horizon)
    if target == "volatility_forecast":
        return torch.nn.functional.softplus(values)
    if target in {"drawdown_risk", "signal_confidence"}:
        return torch.sigmoid(values)
    return values


def _sequence_diagnostics(
    x_time: object,
    hidden: object,
    pooled: object,
    torch: object,
) -> dict[str, object]:
    return {
        "temporal_contribution_summary": _normalize_positive(
            hidden.abs().mean(dim=-1),
            torch,
        ),
        "feature_saliency_placeholder": _normalize_positive(
            x_time.abs().mean(dim=1),
            torch,
        ),
        "latent_state_summary": {
            "sequence_shape": [int(value) for value in hidden.shape],
            "pooled_shape": [int(value) for value in pooled.shape],
            "pooled_mean_abs": pooled.abs().mean(dim=-1).detach().cpu().tolist(),
            "pooled_max_abs": pooled.abs().amax(dim=-1).detach().cpu().tolist(),
        },
    }


def _normalize_positive(value: object, torch: object) -> object:
    denominator = value.sum(dim=-1, keepdim=True).clamp_min(1e-8)
    return torch.nan_to_num(value / denominator)


def _validate_time_input(x_time: object, config: FinMambaConfig) -> None:
    shape = getattr(x_time, "shape", None)
    if shape is None or len(shape) != 3:
        raise ValueError("Invalid x_time; expected tensor shaped [batch, time, features]")
    if int(shape[-1]) != config.input_dim:
        raise ValueError(
            f"Invalid x_time feature dim {int(shape[-1])}; "
            f"expected input_dim={config.input_dim}"
        )


def _validate_time_context(name: str, value: object, hidden: object) -> None:
    shape = getattr(value, "shape", None)
    hidden_shape = getattr(hidden, "shape", None)
    if shape is None or len(shape) != 3:
        raise ValueError(f"Invalid {name}; expected tensor shaped [batch, time, features]")
    if int(shape[0]) != int(hidden_shape[0]) or int(shape[1]) != int(hidden_shape[1]):
        raise ValueError(
            f"Invalid {name} shape {tuple(shape)!r}; expected batch/time to match x_time"
        )


def _validate_asset_context(name: str, value: object) -> None:
    shape = getattr(value, "shape", None)
    if shape is None or len(shape) != 3:
        raise ValueError(f"Invalid {name}; expected tensor shaped [batch, assets, features]")


def _require_positive(name: str, value: int) -> None:
    if value > 0:
        return
    raise ValueError(f"Invalid {name}={value!r}; expected positive integer")
