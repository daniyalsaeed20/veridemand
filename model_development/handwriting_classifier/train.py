"""Staged transfer-learning training loop."""

from __future__ import annotations

from collections.abc import Sequence
from contextlib import suppress
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image

from model_development.handwriting_classifier.config import CLASS_ORDER, TrainConfig
from model_development.handwriting_classifier.dataset import TrainingExample, class_counts
from model_development.handwriting_classifier.model import (
    build_model,
    freeze_features,
    parameter_counts,
    unfreeze_final_blocks,
)
from model_development.handwriting_classifier.transforms import (
    preprocess_for_training,
    tensor_to_torch,
)

LABEL_TO_INDEX = {lab: i for i, lab in enumerate(CLASS_ORDER)}


@dataclass
class ExampleRef:
    path: str
    label: str
    source_group_id: str
    synthetic: bool = False
    crop_id: str = ""


def to_refs(
    examples: Sequence[TrainingExample],
    synthetic: Sequence[dict[str, object]] | None = None,
) -> list[ExampleRef]:
    refs = [
        ExampleRef(
            path=e.crop_path_private,
            label=e.label,
            source_group_id=e.source_group_id,
            synthetic=False,
            crop_id=e.crop_id,
        )
        for e in examples
    ]
    if synthetic:
        for s in synthetic:
            refs.append(
                ExampleRef(
                    path=str(s["path"]),
                    label=str(s["label"]),
                    source_group_id=str(s["source_group_id"]),
                    synthetic=True,
                    crop_id=str(s["crop_id"]),
                )
            )
    return refs


def compute_class_weights(refs: Sequence[ExampleRef]) -> list[float]:
    """Inverse-frequency weights from training fold only."""

    counts = {lab: 0 for lab in CLASS_ORDER}
    for r in refs:
        counts[r.label] = counts.get(r.label, 0) + 1
    total = sum(counts.values()) or 1
    n_classes = len(CLASS_ORDER)
    weights = []
    for lab in CLASS_ORDER:
        c = max(counts[lab], 1)
        weights.append(total / (n_classes * c))
    return weights


class CropDataset:
    def __init__(
        self,
        refs: Sequence[ExampleRef],
        *,
        train: bool,
        config: TrainConfig,
        seed: int,
    ) -> None:
        self.refs = list(refs)
        self.train = train
        self.config = config
        self.seed = seed

    def __len__(self) -> int:
        return len(self.refs)

    def __getitem__(self, index: int) -> tuple[Any, int]:
        import torch

        ref = self.refs[index]
        img = Image.open(ref.path).convert("RGB")
        rng = np.random.default_rng(self.seed + index * 9973) if self.train else None
        arr = preprocess_for_training(
            img,
            rng,
            train=self.train,
            strength=self.config.aug_strength,
        )
        x = tensor_to_torch(arr)
        y = LABEL_TO_INDEX[ref.label]
        return x, torch.tensor(y, dtype=torch.long)


def _seed_everything(config: TrainConfig) -> None:
    import random

    import torch

    random.seed(config.random_seed)
    np.random.seed(config.numpy_seed)
    torch.manual_seed(config.torch_seed)
    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(config.torch_seed)
    with suppress(Exception):
        torch.use_deterministic_algorithms(True)


def _make_loader(
    dataset: CropDataset,
    config: TrainConfig,
    *,
    shuffle: bool,
    class_weights: list[float] | None,
    refs: Sequence[ExampleRef],
) -> Any:
    import torch
    from torch.utils.data import DataLoader, WeightedRandomSampler

    generator = torch.Generator()
    generator.manual_seed(config.dataloader_seed)

    if config.balancing == "balanced_sampler" and shuffle:
        counts = class_counts(
            [
                TrainingExample(
                    schema_version="",
                    training_manifest_version="",
                    crop_id=r.crop_id or str(i),
                    crop_sha256="0" * 64,
                    source_group_id=r.source_group_id,
                    label=r.label,  # type: ignore[arg-type]
                    label_source="prototype_primary_review",
                    review_status="",
                    crop_path_private=r.path,
                    width=1,
                    height=1,
                )
                for i, r in enumerate(refs)
            ]
        )
        # per-sample weight = 1/count(class)
        sample_w = []
        for r in refs:
            sample_w.append(1.0 / max(counts.get(r.label, 1), 1))
        sampler = WeightedRandomSampler(
            weights=sample_w,
            num_samples=len(sample_w),
            replacement=True,
            generator=generator,
        )
        return DataLoader(
            dataset,
            batch_size=config.batch_size,
            sampler=sampler,
            num_workers=config.num_workers,
        )

    return DataLoader(
        dataset,
        batch_size=config.batch_size,
        shuffle=shuffle,
        num_workers=config.num_workers,
        generator=generator if shuffle else None,
    )


def train_model(
    train_refs: Sequence[ExampleRef],
    config: TrainConfig,
    *,
    device: str | None = None,
    checkpoint_path: Path | None = None,
) -> dict[str, Any]:
    """Two-stage transfer learning with fixed epoch budget (no outer-fold ES)."""

    import torch
    import torch.nn as nn

    _seed_everything(config)
    if device is None:
        device = "cuda" if torch.cuda.is_available() else "cpu"

    model = build_model(pretrained=True)
    freeze_features(model)
    model.to(device)

    weights = compute_class_weights(train_refs)
    # When using balanced sampler, use unweighted CE to avoid double compensation.
    if config.balancing == "balanced_sampler":
        criterion: nn.Module = nn.CrossEntropyLoss()
    else:
        criterion = nn.CrossEntropyLoss(
            weight=torch.tensor(weights, dtype=torch.float32, device=device)
        )

    train_ds = CropDataset(train_refs, train=True, config=config, seed=config.random_seed)
    loader = _make_loader(train_ds, config, shuffle=True, class_weights=weights, refs=train_refs)

    history: list[dict[str, float]] = []

    def _run_epochs(epochs: int, lr: float) -> None:
        optimizer = torch.optim.AdamW(
            (p for p in model.parameters() if p.requires_grad),
            lr=lr,
            weight_decay=config.weight_decay,
        )
        model.train()
        for epoch in range(epochs):
            total_loss = 0.0
            n = 0
            for xb, yb in loader:
                xb = xb.to(device)
                yb = yb.to(device)
                optimizer.zero_grad(set_to_none=True)
                logits = model(xb)
                loss = criterion(logits, yb)
                loss.backward()
                optimizer.step()
                total_loss += float(loss.item()) * int(yb.size(0))
                n += int(yb.size(0))
            history.append(
                {"epoch_loss": total_loss / max(n, 1), "lr": lr, "stage_epochs": float(epoch)}
            )

    # Stage 1: head only
    _run_epochs(config.stage1_epochs, config.stage1_lr)
    # Stage 2: unfreeze final blocks
    unfreeze_final_blocks(model, n_blocks=3)
    _run_epochs(config.stage2_epochs, config.stage2_lr)

    if checkpoint_path is not None:
        checkpoint_path.parent.mkdir(parents=True, exist_ok=True)
        torch.save(
            {
                "model_state_dict": model.state_dict(),
                "config": config.to_dict(),
                "class_order": list(CLASS_ORDER),
                "class_weights": weights,
            },
            checkpoint_path,
        )

    return {
        "model": model,
        "device": device,
        "history": history,
        "class_weights": weights,
        "parameter_counts": parameter_counts(model),
        "train_counts": {lab: sum(1 for r in train_refs if r.label == lab) for lab in CLASS_ORDER},
        "effective_examples_per_epoch": len(train_refs),
    }


def predict_logits(
    model: Any,
    refs: Sequence[ExampleRef],
    *,
    device: str,
    batch_size: int = 8,
) -> list[dict[str, Any]]:
    """Run deterministic eval-preprocess inference; return per-example records."""

    import torch
    import torch.nn.functional as F

    model.eval()
    out: list[dict[str, Any]] = []
    with torch.no_grad():
        for start in range(0, len(refs), batch_size):
            chunk = refs[start : start + batch_size]
            tensors = []
            for ref in chunk:
                img = Image.open(ref.path).convert("RGB")
                arr = preprocess_for_training(img, None, train=False)
                tensors.append(tensor_to_torch(arr))
            xb = torch.stack(tensors, dim=0).to(device)
            logits = model(xb)
            probs = F.softmax(logits, dim=1)
            for i, ref in enumerate(chunk):
                logit_row = logits[i].detach().cpu().numpy().astype(np.float64)
                prob_row = probs[i].detach().cpu().numpy().astype(np.float64)
                order = np.argsort(-prob_row)
                top = float(prob_row[order[0]])
                second = float(prob_row[order[1]])
                out.append(
                    {
                        "crop_id": ref.crop_id,
                        "path": ref.path,
                        "label": ref.label,
                        "source_group_id": ref.source_group_id,
                        "synthetic": ref.synthetic,
                        "logits": logit_row.tolist(),
                        "probabilities": prob_row.tolist(),
                        "top_class": CLASS_ORDER[int(order[0])],
                        "top_two_margin": top - second,
                    }
                )
    return out
