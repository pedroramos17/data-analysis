"""MCI-GRU + GNN architecture specification for Sourceflow finance."""

from __future__ import annotations

from dataclasses import dataclass

from sourceflow.config.feature_flags import require_feature


@dataclass(frozen=True, slots=True)
class FinanceModelSpec:
    """Serializable next-generation finance model specification.

    Example:
        `spec = finance_model_spec()`
    """

    temporal_encoder: str
    graph_encoder: str
    latent_state: str
    fusion: str
    loss: str
    xai_boundary: str


def finance_model_spec() -> FinanceModelSpec:
    """Return the documented MCI-GRU + GNN model design.

    Example:
        `spec = finance_model_spec()`
    """
    require_feature("FIN_MODEL_MCI_GRU")
    return FinanceModelSpec(
        temporal_encoder="Improved GRU with reset gate modulated by history attention",
        graph_encoder=(
            "GAT/GNN over relation, corrected-correlation, and exposure edges"
        ),
        latent_state=(
            "K learned latent market state vectors with multi-head cross-attention"
        ),
        fusion=(
            "Concatenate temporal, graph, latent, fundamental, and "
            "multifractal vectors"
        ),
        loss=(
            "direction CE/BCE + Huber return + rank IC + drawdown + "
            "turnover penalties"
        ),
        xai_boundary="No truth claims; only signal evidence and model diagnostics",
    )


def build_torch_prototype() -> object:
    """Build a torch prototype only when the experimental flag is enabled.

    Example:
        `model = build_torch_prototype()`
    """
    require_feature("FIN_MODEL_EXPERIMENTAL_TORCH")
    import torch

    return torch.nn.Identity()
