"""SAMBA-style hybrid sequence blocks for financial time series."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass, field
from pathlib import Path

from src.models.base import (
    BaseForecastModel,
    ForecastDataset,
    ForecastPrediction,
    load_json_payload,
    numeric_value,
    row_asset_id,
    row_symbol,
    row_timestamp,
    save_json_payload,
)
from src.models.explainability import sequence_prediction_explanation, tensor_item
from src.models.sequence._torch import torch_modules

SAMBA_BRANCHES = (
    "local_causal_convolution",
    "state_space_sequence",
    "low_rank_attention",
)


@dataclass(frozen=True, slots=True)
class SambaConfig:
    """Config for a CPU-safe SAMBA-style sequence architecture.

    Example:
        `SambaConfig(input_dim=16, hidden_dim=64, horizon=5)`
    """

    input_dim: int
    hidden_dim: int = 64
    num_layers: int = 2
    dropout: float = 0.0
    horizon: int = 1
    output_dim: int = 1
    kernel_size: int = 3
    attention_rank: int = 16
    attention_stride: int = 4
    asset_conditioning: bool = True

    def __post_init__(self) -> None:
        """Validate config values early without importing PyTorch."""
        _require_positive("input_dim", self.input_dim)
        _require_positive("hidden_dim", self.hidden_dim)
        _require_positive("num_layers", self.num_layers)
        _require_positive("horizon", self.horizon)
        _require_positive("output_dim", self.output_dim)
        _require_positive("kernel_size", self.kernel_size)
        _require_positive("attention_rank", self.attention_rank)
        _require_positive("attention_stride", self.attention_stride)
        if not 0.0 <= self.dropout < 1.0:
            raise ValueError("Invalid dropout; expected 0 <= dropout < 1")


@dataclass(frozen=True, slots=True)
class SambaBlock:
    """Builder for one SAMBA hybrid sequence block.

    Example:
        `block = SambaBlock(SambaConfig(input_dim=8)).build()`
    """

    config: SambaConfig

    def architecture_metadata(self) -> dict[str, object]:
        """Return architecture metadata without importing PyTorch."""
        return {
            "architecture": "samba",
            "components": [
                "local_causal_convolution_branch",
                "causal_convolution",
                "state_space_sequence_block",
                "mamba_branch",
                "sparse_attention_branch",
                "low_rank_attention_branch",
                "gated_mixing",
                "gated_fusion",
                "residual_normalization",
                "cross_asset_conditioning",
                "regime_embedding",
                "feature_projection",
                "prediction_head",
                "branch_contribution_weights",
                "feature_saliency_placeholder",
                "temporal_contribution_summary",
            ],
            "branches": list(SAMBA_BRANCHES),
            "config": asdict(self.config),
        }

    def build(self) -> object:
        """Build the optional PyTorch SAMBA block."""
        torch, nn = torch_modules("SAMBA block")
        config = self.config

        class _StateSpaceBranch(nn.Module):
            """Selective state-space placeholder using causal cumulative dynamics."""

            def __init__(self) -> None:
                super().__init__()
                self.select_gate = nn.Linear(config.hidden_dim, config.hidden_dim)
                self.update = nn.Linear(config.hidden_dim, config.hidden_dim)
                self.output = nn.Linear(config.hidden_dim, config.hidden_dim)

            def forward(self, hidden: object) -> object:
                selected = torch.sigmoid(self.select_gate(hidden))
                update = torch.tanh(self.update(hidden)) * selected
                state = torch.cumsum(update, dim=1)
                return self.output(torch.tanh(state))

        class _LowRankAttentionBranch(nn.Module):
            """Low-rank strided attention branch for long noisy sequences."""

            def __init__(self) -> None:
                super().__init__()
                self.query = nn.Linear(config.hidden_dim, config.attention_rank)
                self.key = nn.Linear(config.hidden_dim, config.attention_rank)
                self.value = nn.Linear(config.hidden_dim, config.attention_rank)
                self.output = nn.Linear(config.attention_rank, config.hidden_dim)

            def forward(self, hidden: object) -> tuple[object, object]:
                memory = hidden[:, :: config.attention_stride, :]
                query = self.query(hidden)
                key = self.key(memory)
                value = self.value(memory)
                scores = torch.matmul(query, key.transpose(-1, -2))
                scores = scores / config.attention_rank**0.5
                weights = torch.softmax(scores, dim=-1)
                context = torch.matmul(weights, value)
                return self.output(context), weights

        class _SambaBlockModule(nn.Module):
            """Causal conv, state-space, and low-rank attention fusion block."""

            def __init__(self) -> None:
                super().__init__()
                self.pre_norm = nn.LayerNorm(config.hidden_dim)
                self.local_conv = nn.Conv1d(
                    config.hidden_dim,
                    config.hidden_dim,
                    config.kernel_size,
                    padding=config.kernel_size - 1,
                    groups=config.hidden_dim,
                )
                self.local_projection = nn.Linear(config.hidden_dim, config.hidden_dim)
                self.state_space = _StateSpaceBranch()
                self.attention = _LowRankAttentionBranch()
                self.branch_gate = nn.Linear(config.hidden_dim, len(SAMBA_BRANCHES))
                self.cross_fusion = nn.Linear(config.hidden_dim, config.hidden_dim)
                self.dropout = nn.Dropout(config.dropout)
                self.residual_norm = nn.LayerNorm(config.hidden_dim)

            def forward(
                self,
                hidden: object,
                cross_context: object | None = None,
                return_diagnostics: bool = False,
            ) -> dict[str, object]:
                normalized = self.pre_norm(hidden)
                local = self.local_conv(normalized.transpose(1, 2)).transpose(1, 2)
                local = self.local_projection(local[:, : normalized.shape[1], :])
                state = self.state_space(normalized)
                attention, attention_weights = self.attention(normalized)
                branches = torch.stack([local, state, attention], dim=-2)
                branch_weights = torch.softmax(self.branch_gate(normalized), dim=-1)
                fused = torch.sum(branches * branch_weights.unsqueeze(-1), dim=-2)
                if cross_context is not None:
                    fused = fused + self.cross_fusion(cross_context).unsqueeze(1)
                encoded = self.residual_norm(hidden + self.dropout(fused))
                diagnostics: dict[str, object] = {}
                if return_diagnostics:
                    diagnostics = _block_diagnostics(
                        encoded,
                        branch_weights,
                        attention_weights,
                        torch,
                    )
                return {"encoded": encoded, "diagnostics": diagnostics}

        return _SambaBlockModule()


@dataclass(frozen=True, slots=True)
class SambaEncoder:
    """Builder for a stack of SAMBA blocks usable as a drop-in encoder."""

    config: SambaConfig

    def architecture_metadata(self) -> dict[str, object]:
        """Return encoder metadata without importing PyTorch."""
        block_metadata = SambaBlock(self.config).architecture_metadata()
        return block_metadata | {"encoder_layers": self.config.num_layers}

    def build(self) -> object:
        """Build the optional PyTorch SAMBA encoder."""
        torch, nn = torch_modules("SAMBA encoder")
        config = self.config
        block_builder = SambaBlock(config)

        class _SambaEncoderModule(nn.Module):
            """Input projection plus repeated SAMBA hybrid blocks."""

            def __init__(self) -> None:
                super().__init__()
                self.input_projection = nn.Linear(config.input_dim, config.hidden_dim)
                self.input_norm = nn.LayerNorm(config.hidden_dim)
                self.blocks = nn.ModuleList(
                    [block_builder.build() for _ in range(config.num_layers)]
                )
                self.cross_projection = nn.LazyLinear(config.hidden_dim)
                self.cross_query = nn.Linear(config.hidden_dim, config.hidden_dim)
                self.cross_key = nn.Linear(config.hidden_dim, config.hidden_dim)
                self.cross_value = nn.Linear(config.hidden_dim, config.hidden_dim)

            def forward(
                self,
                x_time: object,
                x_cross: object | None = None,
                return_diagnostics: bool = False,
            ) -> dict[str, object]:
                _validate_time_input(x_time, config)
                hidden = self.input_norm(self.input_projection(x_time))
                diagnostics: dict[str, object] = {}
                cross_context = self._cross_asset_context(
                    hidden,
                    x_cross,
                    diagnostics,
                    return_diagnostics,
                )
                branch_weights: list[object] = []
                for block in self.blocks:
                    result = block(
                        hidden,
                        cross_context=cross_context,
                        return_diagnostics=return_diagnostics,
                    )
                    hidden = result["encoded"]
                    block_diagnostics = result["diagnostics"]
                    if block_diagnostics:
                        branch_weights.append(
                            block_diagnostics["branch_contribution_weights"]
                        )
                pooled = hidden[:, -1, :]
                if return_diagnostics:
                    diagnostics |= _encoder_diagnostics(
                        x_time,
                        hidden,
                        branch_weights,
                        torch,
                    )
                output: dict[str, object] = {
                    "encoded": hidden,
                    "pooled": pooled,
                }
                if return_diagnostics:
                    output["diagnostics"] = diagnostics
                return output

            def _cross_asset_context(
                self,
                hidden: object,
                x_cross: object | None,
                diagnostics: dict[str, object],
                return_diagnostics: bool,
            ) -> object | None:
                if not config.asset_conditioning or x_cross is None:
                    return None
                _validate_asset_context("x_cross", x_cross, hidden)
                tokens = self.cross_projection(x_cross)
                query = self.cross_query(hidden[:, -1, :]).unsqueeze(-1)
                key = self.cross_key(tokens)
                value = self.cross_value(tokens)
                scores = torch.matmul(key, query).squeeze(-1) / config.hidden_dim**0.5
                weights = torch.softmax(scores, dim=1)
                context = torch.sum(value * weights.unsqueeze(-1), dim=1)
                if return_diagnostics:
                    diagnostics["cross_asset_weights"] = weights
                    diagnostics["cross_asset_context"] = context
                return context

        return _SambaEncoderModule()


@dataclass(slots=True)
class SambaForecastModel(BaseForecastModel):
    """Registry-friendly SAMBA forecast model wrapper.

    Example:
        `build_default_model_registry().create("samba", {"input_dim": 8})`
    """

    config: SambaConfig
    model_version: str = "local-samba-v1"
    feature_columns: tuple[str, ...] = field(default_factory=tuple)
    _module: object | None = field(default=None, init=False, repr=False)

    @classmethod
    def from_config(cls, config: Mapping[str, object]) -> "SambaForecastModel":
        """Create a SAMBA forecast model from registry config."""
        model_config = _config_from_mapping(config)
        feature_columns = tuple(str(value) for value in config.get("feature_columns", ()))
        return cls(
            model_config,
            model_version=str(config.get("model_version", "local-samba-v1")),
            feature_columns=feature_columns,
        )

    def build(self) -> object:
        """Build the optional PyTorch SAMBA forecasting module."""
        torch, nn = torch_modules("SAMBA forecast model")
        config = self.config
        encoder_builder = SambaEncoder(config)

        class _SambaForecastModule(nn.Module):
            """Forecast and uncertainty heads over a SAMBA encoder."""

            def __init__(self) -> None:
                super().__init__()
                self.encoder = encoder_builder.build()
                self.forecast_head = nn.Linear(
                    config.hidden_dim,
                    config.horizon * config.output_dim,
                )
                self.uncertainty_head = nn.Linear(
                    config.hidden_dim,
                    config.horizon * config.output_dim,
                )

            def forward(
                self,
                x_time: object,
                x_cross: object | None = None,
                return_diagnostics: bool = True,
            ) -> dict[str, object]:
                encoded = self.encoder(
                    x_time,
                    x_cross=x_cross,
                    return_diagnostics=return_diagnostics,
                )
                pooled = encoded["pooled"]
                forecast = self.forecast_head(pooled).reshape(
                    pooled.shape[0],
                    config.horizon,
                    config.output_dim,
                )
                uncertainty = torch.nn.functional.softplus(
                    self.uncertainty_head(pooled)
                ).reshape(pooled.shape[0], config.horizon, config.output_dim)
                return {
                    "forecast": forecast,
                    "uncertainty_proxy": uncertainty,
                    "branch_diagnostics": encoded.get("diagnostics", {}),
                    "latent_states": {
                        "sequence": encoded["encoded"],
                        "pooled": pooled,
                    },
                }

        return _SambaForecastModule()

    def fit(
        self,
        dataset: ForecastDataset,
        config: Mapping[str, object],
    ) -> "SambaForecastModel":
        """Record feature columns for a future training loop."""
        configured = tuple(str(value) for value in config.get("feature_columns", ()))
        self.feature_columns = configured or _infer_feature_columns(
            dataset,
            self.config.input_dim,
        )
        return self

    def predict(
        self,
        dataset: ForecastDataset,
        horizon: int | str,
    ) -> list[ForecastPrediction]:
        """Run CPU-safe inference from row dictionaries when PyTorch is installed."""
        if not dataset:
            return []
        torch, _nn = torch_modules("SAMBA forecast model")
        feature_columns = self.feature_columns or _infer_feature_columns(
            dataset,
            self.config.input_dim,
        )
        x_time = _dataset_tensor(torch, dataset, feature_columns, self.config.input_dim)
        module = self._module or self.build()
        self._module = module
        module.eval()
        with torch.no_grad():
            output = module(x_time, return_diagnostics=True)
        forecast = output["forecast"][:, 0, 0].detach().cpu().tolist()
        uncertainty = output["uncertainty_proxy"][:, 0, 0].detach().cpu().tolist()
        diagnostics = output.get("branch_diagnostics", {})
        return [
            ForecastPrediction(
                symbol=row_symbol(row),
                ts=row_timestamp(row),
                horizon=str(horizon),
                prediction=float(value),
                signal=float(value),
                confidence=_confidence_from_uncertainty(uncertainty[index]),
                model_name="samba_forecast",
                model_version=self.model_version,
                explanation_json=sequence_prediction_explanation(
                    architecture="samba",
                    feature_columns=feature_columns,
                    temporal_contribution=tensor_item(
                        diagnostics.get("temporal_contribution_summary"),
                        index,
                    ),
                    feature_saliency=tensor_item(
                        diagnostics.get("feature_saliency_placeholder"),
                        index,
                    ),
                    branch_names=SAMBA_BRANCHES,
                    branch_contribution=tensor_item(
                        diagnostics.get("branch_contribution_summary"),
                        index,
                    ),
                    uncertainty_proxy=uncertainty[index],
                ),
                asset_id=row_asset_id(row),
            )
            for index, (row, value) in enumerate(zip(dataset, forecast, strict=True))
        ]

    def explain(
        self,
        dataset: ForecastDataset,
        predictions: Sequence[ForecastPrediction],
    ) -> dict[str, object]:
        """Return placeholder explainability metadata for forecast rows."""
        return {
            "architecture": "samba",
            "branch_names": list(SAMBA_BRANCHES),
            "feature_saliency": "placeholder_from_absolute_feature_magnitude",
            "temporal_contribution": "placeholder_from_latent_state_magnitude",
            "rows": len(dataset),
            "predictions": len(predictions),
        }

    def save(self, path: str | Path) -> Path:
        """Save registry-friendly SAMBA config metadata as JSON."""
        return save_json_payload(
            path,
            {
                "config": asdict(self.config),
                "feature_columns": list(self.feature_columns),
                "model_version": self.model_version,
            },
        )

    @classmethod
    def load(cls, path: str | Path) -> "SambaForecastModel":
        """Load SAMBA config metadata from JSON."""
        payload = load_json_payload(path)
        config = _config_from_mapping(payload.get("config", {}))
        return cls(
            config,
            model_version=str(payload.get("model_version", "local-samba-v1")),
            feature_columns=tuple(payload.get("feature_columns", ())),
        )

    def metadata(self) -> dict[str, object]:
        """Return model metadata for registry manifests."""
        return {
            "model_name": "samba_forecast",
            "model_version": self.model_version,
            "architecture": "samba",
            "requires_gpu": False,
            "requires_torch": True,
            "config": asdict(self.config),
            "feature_columns": list(self.feature_columns),
            "branches": list(SAMBA_BRANCHES),
        }


def _block_diagnostics(
    encoded: object,
    branch_weights: object,
    attention_weights: object,
    torch: object,
) -> dict[str, object]:
    return {
        "branch_names": list(SAMBA_BRANCHES),
        "branch_contribution_weights": branch_weights,
        "branch_contribution_summary": branch_weights.mean(dim=1),
        "attention_weights": attention_weights,
        "feature_saliency_placeholder": _normalize_positive(
            encoded.abs().mean(dim=1),
            torch,
        ),
        "temporal_contribution_summary": _temporal_contribution(encoded, torch),
    }


def _encoder_diagnostics(
    x_time: object,
    hidden: object,
    branch_weights: list[object],
    torch: object,
) -> dict[str, object]:
    diagnostics: dict[str, object] = {
        "branch_names": list(SAMBA_BRANCHES),
        "feature_saliency_placeholder": _normalize_positive(
            x_time.abs().mean(dim=1),
            torch,
        ),
        "temporal_contribution_summary": _temporal_contribution(hidden, torch),
    }
    if branch_weights:
        stacked = torch.stack(branch_weights, dim=0)
        diagnostics["branch_contribution_weights"] = stacked
        diagnostics["branch_contribution_summary"] = stacked.mean(dim=(0, 2))
    return diagnostics


def _temporal_contribution(hidden: object, torch: object) -> object:
    return _normalize_positive(hidden.abs().mean(dim=-1), torch)


def _normalize_positive(value: object, torch: object) -> object:
    denominator = value.sum(dim=-1, keepdim=True).clamp_min(1e-8)
    return torch.nan_to_num(value / denominator)


def _config_from_mapping(config: Mapping[str, object]) -> SambaConfig:
    return SambaConfig(
        input_dim=int(config.get("input_dim", 1)),
        hidden_dim=int(config.get("hidden_dim", 64)),
        num_layers=int(config.get("num_layers", 2)),
        dropout=float(config.get("dropout", 0.0)),
        horizon=int(config.get("horizon", 1)),
        output_dim=int(config.get("output_dim", 1)),
        kernel_size=int(config.get("kernel_size", 3)),
        attention_rank=int(config.get("attention_rank", 16)),
        attention_stride=int(config.get("attention_stride", 4)),
        asset_conditioning=bool(config.get("asset_conditioning", True)),
    )


def _dataset_tensor(
    torch: object,
    dataset: ForecastDataset,
    feature_columns: tuple[str, ...],
    input_dim: int,
) -> object:
    rows = [
        [numeric_value(row.get(column), 0.0) for column in feature_columns[:input_dim]]
        for row in dataset
    ]
    padded = [row + [0.0] * max(0, input_dim - len(row)) for row in rows]
    return torch.tensor(padded, dtype=torch.float32).unsqueeze(1)


def _infer_feature_columns(
    dataset: ForecastDataset,
    input_dim: int,
) -> tuple[str, ...]:
    excluded = {
        "asset_id",
        "confidence",
        "date",
        "prediction",
        "signal",
        "symbol",
        "target",
        "timestamp",
        "ts",
    }
    names: list[str] = []
    for row in dataset:
        for key, value in row.items():
            if key in excluded or key in names:
                continue
            try:
                float(value)
            except (TypeError, ValueError):
                continue
            names.append(str(key))
            if len(names) == input_dim:
                return tuple(names)
    while len(names) < input_dim:
        names.append(f"__zero_{len(names)}")
    return tuple(names)


def _confidence_from_uncertainty(value: object) -> float:
    uncertainty = max(0.0, numeric_value(value, 0.0))
    return 1.0 / (1.0 + uncertainty)


def _validate_time_input(x_time: object, config: SambaConfig) -> None:
    shape = getattr(x_time, "shape", None)
    if shape is None or len(shape) != 3:
        raise ValueError("Invalid x_time; expected tensor shaped [batch, time, features]")
    if int(shape[-1]) != config.input_dim:
        raise ValueError(
            f"Invalid x_time feature dim {int(shape[-1])}; "
            f"expected input_dim={config.input_dim}"
        )


def _validate_asset_context(name: str, value: object, hidden: object) -> None:
    shape = getattr(value, "shape", None)
    hidden_shape = getattr(hidden, "shape", None)
    if shape is None or len(shape) != 3:
        raise ValueError(f"Invalid {name}; expected tensor shaped [batch, assets, features]")
    if int(shape[0]) != int(hidden_shape[0]):
        raise ValueError(
            f"Invalid {name} batch {int(shape[0])}; expected {int(hidden_shape[0])}"
        )


def _require_positive(name: str, value: int) -> None:
    if value > 0:
        return
    raise ValueError(f"Invalid {name}={value!r}; expected positive integer")
