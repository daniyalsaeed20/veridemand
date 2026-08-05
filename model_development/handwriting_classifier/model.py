"""MobileNetV3-Small route-first writing-style classifier."""

from __future__ import annotations

from typing import Any

from model_development.handwriting_classifier import ROUTE_ORDER


def build_model(*, pretrained: bool = True) -> Any:
    """Return MobileNetV3-Small with a 2-logit independent route head."""

    import torch.nn as nn
    from torchvision.models import MobileNet_V3_Small_Weights, mobilenet_v3_small

    weights = MobileNet_V3_Small_Weights.DEFAULT if pretrained else None
    model = mobilenet_v3_small(weights=weights)
    in_features = model.classifier[-1].in_features
    model.classifier[-1] = nn.Linear(in_features, len(ROUTE_ORDER))
    return model


def parameter_counts(model: Any) -> dict[str, int]:
    total = sum(p.numel() for p in model.parameters())
    trainable = sum(p.numel() for p in model.parameters() if p.requires_grad)
    return {"total": int(total), "trainable": int(trainable)}


def freeze_features(model: Any) -> None:
    for name, param in model.named_parameters():
        if name.startswith("classifier"):
            param.requires_grad = True
        else:
            param.requires_grad = False


def unfreeze_final_blocks(model: Any, *, n_blocks: int = 3) -> None:
    """Unfreeze classifier + last n feature blocks for stage-2 fine-tune."""

    for param in model.parameters():
        param.requires_grad = False
    features = model.features
    for block in list(features.children())[-n_blocks:]:
        for param in block.parameters():
            param.requires_grad = True
    for param in model.classifier.parameters():
        param.requires_grad = True


def load_checkpoint(model: Any, path: str | Any, map_location: str = "cpu") -> Any:
    import torch

    state = torch.load(path, map_location=map_location, weights_only=True)
    if isinstance(state, dict) and "model_state_dict" in state:
        model.load_state_dict(state["model_state_dict"])
    else:
        model.load_state_dict(state)
    return model


def weights_provenance() -> dict[str, str]:
    from torchvision.models import MobileNet_V3_Small_Weights

    w = MobileNet_V3_Small_Weights.DEFAULT
    meta = getattr(w, "meta", {}) or {}
    url = ""
    try:
        url = str(w.url)
    except Exception:
        url = str(meta.get("url", ""))
    return {
        "architecture": "mobilenet_v3_small",
        "weights_enum": "MobileNet_V3_Small_Weights.DEFAULT",
        "url": url,
        "categories": str(meta.get("categories", "ImageNet")),
        "licence": "BSD-3-Clause (torchvision) / ImageNet pretrained weights per Torchvision",
        "head": "route_first_linear_2",
        "output_semantics": "route_first_independent_logits",
    }
