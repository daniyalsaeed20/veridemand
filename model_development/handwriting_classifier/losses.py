"""Independent binary losses for dual-risk handwriting / non-text heads."""

from __future__ import annotations

from typing import Any


def compute_pos_weights(targets: Any) -> Any:
    """Fold-derived positive class weights for each risk head.

    ``targets`` shape ``[N, 2]`` with columns handwriting / non_text.
    """

    import torch

    if targets.ndim != 2 or targets.shape[1] != 2:
        raise ValueError("targets must have shape [N, 2]")
    weights: list[float] = []
    n = float(targets.shape[0])
    for col in range(2):
        pos = float(targets[:, col].sum().item())
        neg = n - pos
        weights.append(neg / pos if pos > 0 else 1.0)
    return torch.tensor(weights, dtype=torch.float32, device=targets.device)


def weighted_bce_with_logits(
    logits: Any,
    targets: Any,
    *,
    pos_weight: Any | None = None,
    reduction: str = "mean",
) -> Any:
    """Configuration A — per-head BCEWithLogitsLoss with optional pos_weight."""

    import torch.nn.functional as F

    return F.binary_cross_entropy_with_logits(
        logits,
        targets,
        pos_weight=pos_weight,
        reduction=reduction,
    )


def asymmetric_weighted_bce(
    logits: Any,
    targets: Any,
    *,
    pos_weight: Any | None = None,
    handwriting_fn_multiplier: float = 3.0,
    reduction: str = "mean",
) -> Any:
    """Configuration B — raise handwriting false-negative penalty beyond balancing.

    Applies an extra multiplicative weight on positive handwriting targets so
    missed handwriting (FN) is penalised more than basic pos_weight balancing.
    """

    import torch
    import torch.nn.functional as F

    if handwriting_fn_multiplier < 1.0:
        raise ValueError("handwriting_fn_multiplier must be >= 1.0")

    element = F.binary_cross_entropy_with_logits(
        logits,
        targets,
        pos_weight=pos_weight,
        reduction="none",
    )
    weights = torch.ones_like(element)
    weights[:, 0] = torch.where(
        targets[:, 0] > 0.5,
        torch.full_like(weights[:, 0], float(handwriting_fn_multiplier)),
        weights[:, 0],
    )
    weighted = element * weights
    if reduction == "none":
        return weighted
    if reduction == "sum":
        return weighted.sum()
    return weighted.mean()


def binary_focal_loss_with_logits(
    logits: Any,
    targets: Any,
    *,
    alpha: float = 0.25,
    gamma: float = 2.0,
    pos_weight: Any | None = None,
    reduction: str = "mean",
) -> Any:
    """Configuration C — numerically stable binary focal loss from logits.

    Uses Torch primitives only (no external focal-loss package).
    """

    import torch
    import torch.nn.functional as F

    bce = F.binary_cross_entropy_with_logits(
        logits,
        targets,
        pos_weight=pos_weight,
        reduction="none",
    )
    probs = torch.sigmoid(logits)
    p_t = probs * targets + (1.0 - probs) * (1.0 - targets)
    p_t = p_t.clamp(min=1e-8, max=1.0 - 1e-8)
    alpha_t = alpha * targets + (1.0 - alpha) * (1.0 - targets)
    focal = alpha_t * torch.pow(1.0 - p_t, gamma) * bce
    if reduction == "none":
        return focal
    if reduction == "sum":
        return focal.sum()
    return focal.mean()


def build_criterion(
    loss_name: str,
    *,
    pos_weight: Any | None,
    handwriting_fn_multiplier: float = 3.0,
    focal_alpha: float = 0.25,
    focal_gamma: float = 2.0,
) -> Any:
    """Return a callable ``(logits, targets) -> loss`` for the named config."""

    name = loss_name.lower().strip()

    def _weighted(logits: Any, targets: Any) -> Any:
        return weighted_bce_with_logits(logits, targets, pos_weight=pos_weight)

    def _asymmetric(logits: Any, targets: Any) -> Any:
        return asymmetric_weighted_bce(
            logits,
            targets,
            pos_weight=pos_weight,
            handwriting_fn_multiplier=handwriting_fn_multiplier,
        )

    def _focal(logits: Any, targets: Any) -> Any:
        return binary_focal_loss_with_logits(
            logits,
            targets,
            alpha=focal_alpha,
            gamma=focal_gamma,
            pos_weight=pos_weight,
        )

    if name in ("weighted_bce", "bce", "weighted_bce_with_logits"):
        return _weighted
    if name in ("asymmetric_bce", "asymmetric_weighted_bce"):
        return _asymmetric
    if name in ("focal", "binary_focal", "focal_bce"):
        return _focal
    raise ValueError(f"Unknown loss configuration: {loss_name}")
