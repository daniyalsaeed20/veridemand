"""Independent binary losses for route-first vision_required / handwriting_present."""

from __future__ import annotations

from typing import Any


def compute_pos_weights(targets: Any, hw_mask: Any | None = None) -> Any:
    """Fold-derived positive class weights for each route head.

    ``targets`` shape ``[N, 2]`` with columns vision_required / handwriting_present.
    When ``hw_mask`` is provided, handwriting pos_weight uses only unmasked rows.
    """

    import torch

    if targets.ndim != 2 or targets.shape[1] != 2:
        raise ValueError("targets must have shape [N, 2]")
    weights: list[float] = []
    # Column 0: vision_required — all examples.
    n0 = float(targets.shape[0])
    pos0 = float(targets[:, 0].sum().item())
    neg0 = n0 - pos0
    weights.append(neg0 / pos0 if pos0 > 0 else 1.0)

    # Column 1: handwriting_present — mask uncertain out of weight estimation.
    if hw_mask is not None:
        mask = hw_mask.reshape(-1) > 0.5
        if int(mask.sum().item()) == 0:
            weights.append(1.0)
        else:
            col = targets[mask, 1]
            n1 = float(col.shape[0])
            pos1 = float(col.sum().item())
            neg1 = n1 - pos1
            weights.append(neg1 / pos1 if pos1 > 0 else 1.0)
    else:
        n1 = float(targets.shape[0])
        pos1 = float(targets[:, 1].sum().item())
        neg1 = n1 - pos1
        weights.append(neg1 / pos1 if pos1 > 0 else 1.0)
    return torch.tensor(weights, dtype=torch.float32, device=targets.device)


def weighted_bce_with_logits(
    logits: Any,
    targets: Any,
    *,
    pos_weight: Any | None = None,
    reduction: str = "mean",
) -> Any:
    """Per-head BCEWithLogitsLoss with optional pos_weight."""

    import torch.nn.functional as F

    return F.binary_cross_entropy_with_logits(
        logits,
        targets,
        pos_weight=pos_weight,
        reduction=reduction,
    )


def asymmetric_vision_bce(
    logits: Any,
    targets: Any,
    *,
    pos_weight: Any | None = None,
    vision_fn_multiplier: float = 3.0,
    reduction: str = "mean",
) -> Any:
    """Raise vision_required false-negative penalty (unsafe region predicted safe)."""

    import torch
    import torch.nn.functional as F

    if vision_fn_multiplier < 1.0:
        raise ValueError("vision_fn_multiplier must be >= 1.0")

    element = F.binary_cross_entropy_with_logits(
        logits,
        targets,
        pos_weight=pos_weight,
        reduction="none",
    )
    weights = torch.ones_like(element)
    weights[:, 0] = torch.where(
        targets[:, 0] > 0.5,
        torch.full_like(weights[:, 0], float(vision_fn_multiplier)),
        weights[:, 0],
    )
    weighted = element * weights
    if reduction == "none":
        return weighted
    if reduction == "sum":
        return weighted.sum()
    return weighted.mean()


# Alias kept so older imports of asymmetric_weighted_bce still resolve.
asymmetric_weighted_bce = asymmetric_vision_bce


def binary_focal_loss_with_logits(
    logits: Any,
    targets: Any,
    *,
    alpha: float = 0.25,
    gamma: float = 2.0,
    pos_weight: Any | None = None,
    reduction: str = "mean",
) -> Any:
    """Numerically stable binary focal loss from logits (Torch primitives only)."""

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


def route_first_combined_loss(
    logits: Any,
    targets: Any,
    hw_mask: Any,
    *,
    loss_name: str,
    pos_weight: Any | None = None,
    vision_fn_multiplier: float = 3.0,
    focal_alpha: float = 0.25,
    focal_gamma: float = 2.0,
    route_loss_weight: float = 1.0,
    handwriting_loss_weight: float = 0.5,
) -> Any:
    """Combine route and handwriting losses with uncertain HW masking.

    Uncertain examples (hw_mask == 0) do not contribute to the handwriting head.
    When a batch is fully masked for HW, that head contributes 0 (numerically stable).
    """

    import torch

    name = loss_name.lower().strip()
    route_logits = logits[:, 0:1]
    route_targets = targets[:, 0:1]
    hw_logits = logits[:, 1:2]
    hw_targets = targets[:, 1:2]
    mask = hw_mask.reshape(-1, 1).to(dtype=logits.dtype)

    pw_route = None if pos_weight is None else pos_weight[0:1]
    pw_hw = None if pos_weight is None else pos_weight[1:2]

    if name in ("weighted_bce", "bce", "weighted_bce_with_logits"):
        route_elem = weighted_bce_with_logits(
            route_logits, route_targets, pos_weight=pw_route, reduction="none"
        )
        hw_elem = weighted_bce_with_logits(
            hw_logits, hw_targets, pos_weight=pw_hw, reduction="none"
        )
    elif name in ("asymmetric_bce", "asymmetric_weighted_bce", "asymmetric_vision_bce"):
        # Asymmetric penalty only on the vision_required column.
        both = asymmetric_vision_bce(
            logits,
            targets,
            pos_weight=pos_weight,
            vision_fn_multiplier=vision_fn_multiplier,
            reduction="none",
        )
        route_elem = both[:, 0:1]
        hw_elem = weighted_bce_with_logits(
            hw_logits, hw_targets, pos_weight=pw_hw, reduction="none"
        )
    elif name in ("focal", "binary_focal", "focal_bce"):
        route_elem = binary_focal_loss_with_logits(
            route_logits,
            route_targets,
            alpha=focal_alpha,
            gamma=focal_gamma,
            pos_weight=pw_route,
            reduction="none",
        )
        hw_elem = weighted_bce_with_logits(
            hw_logits, hw_targets, pos_weight=pw_hw, reduction="none"
        )
    else:
        raise ValueError(f"Unknown loss configuration: {loss_name}")

    l_route = route_elem.mean()
    mask_sum = mask.sum()
    if float(mask_sum.item()) > 0:
        l_hw = (hw_elem * mask).sum() / mask_sum
    else:
        l_hw = torch.zeros((), dtype=logits.dtype, device=logits.device)

    return float(route_loss_weight) * l_route + float(handwriting_loss_weight) * l_hw


def build_criterion(
    loss_name: str,
    *,
    pos_weight: Any | None,
    handwriting_fn_multiplier: float = 3.0,
    vision_fn_multiplier: float | None = None,
    focal_alpha: float = 0.25,
    focal_gamma: float = 2.0,
    route_loss_weight: float = 1.0,
    handwriting_loss_weight: float = 0.5,
) -> Any:
    """Return ``(logits, targets, hw_mask) -> loss`` for the named config."""

    fn_mult = (
        float(vision_fn_multiplier)
        if vision_fn_multiplier is not None
        else float(handwriting_fn_multiplier)
    )

    def _criterion(logits: Any, targets: Any, hw_mask: Any) -> Any:
        return route_first_combined_loss(
            logits,
            targets,
            hw_mask,
            loss_name=loss_name,
            pos_weight=pos_weight,
            vision_fn_multiplier=fn_mult,
            focal_alpha=focal_alpha,
            focal_gamma=focal_gamma,
            route_loss_weight=route_loss_weight,
            handwriting_loss_weight=handwriting_loss_weight,
        )

    return _criterion
