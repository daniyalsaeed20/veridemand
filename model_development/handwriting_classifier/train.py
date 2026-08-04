"""Staged transfer-learning training loop (dual-risk heads)."""

from __future__ import annotations

from collections.abc import Sequence
from contextlib import suppress
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image

from model_development.handwriting_classifier import RISK_ORDER, TRAINING_LABELS
from model_development.handwriting_classifier.config import (
    TrainConfig,
    risk_target_for_label,
)
from model_development.handwriting_classifier.dataset import TrainingExample, class_counts
from model_development.handwriting_classifier.losses import build_criterion, compute_pos_weights
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

HARD_EXAMPLE_TAGS = frozenset({"signature", "cursive", "digits", "hand_printed", "longer_note"})


@dataclass
class ExampleRef:
    path: str
    label: str
    source_group_id: str
    synthetic: bool = False
    crop_id: str = ""
    public: bool = False
    # When True, this is a project (non-public) handwritten crop.
    project_handwriting: bool = False
    source_category: str = ""


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
            public=False,
            project_handwriting=(e.label == "handwritten"),
            source_category=getattr(e, "source_category", "") or "",
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
                    public=False,
                    project_handwriting=False,
                    source_category="",
                )
            )
    return refs


def _category_tags(source_category: str) -> set[str]:
    if not source_category:
        return set()
    return {p.strip() for p in source_category.split(",") if p.strip()}


def is_hard_project_example(ref: ExampleRef) -> bool:
    """A-priori hard categories (signature/cursive/etc.) — never mined from OOF."""

    if ref.public or ref.synthetic:
        return False
    tags = _category_tags(ref.source_category)
    if ref.label == "handwritten" and (tags & HARD_EXAMPLE_TAGS):
        return True
    return ref.label == "non_text" and not ref.synthetic


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
        # Reject uncertain/excluded at dataset construction.
        for ref in self.refs:
            if ref.label not in TRAINING_LABELS:
                raise ValueError(
                    f"Label {ref.label!r} is not eligible for dual-risk training "
                    "(uncertain/excluded are rejected)."
                )

    def __len__(self) -> int:
        return len(self.refs)

    def __getitem__(self, index: int) -> tuple[Any, Any]:
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
        hw, nt = risk_target_for_label(ref.label)
        y = torch.tensor([hw, nt], dtype=torch.float32)
        return x, y


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


def _sample_weights(refs: Sequence[ExampleRef], config: TrainConfig) -> list[float]:
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
    sample_w: list[float] = []
    for r in refs:
        base = 1.0 / max(counts.get(r.label, 1), 1)
        if config.hard_example_emphasis and is_hard_project_example(r):
            base *= float(config.hard_example_multiplier)
        sample_w.append(base)
    return sample_w


def _make_loader(
    dataset: CropDataset,
    config: TrainConfig,
    *,
    shuffle: bool,
    refs: Sequence[ExampleRef],
) -> Any:
    import torch
    from torch.utils.data import DataLoader, WeightedRandomSampler

    generator = torch.Generator()
    generator.manual_seed(config.dataloader_seed)

    if shuffle:
        # Always use inverse-frequency sample weights; optionally amplify hard tags.
        sample_w = _sample_weights(refs, config)
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


def _targets_tensor(refs: Sequence[ExampleRef]) -> Any:
    import torch

    rows = [risk_target_for_label(r.label) for r in refs]
    return torch.tensor(rows, dtype=torch.float32)


def train_model(
    train_refs: Sequence[ExampleRef],
    config: TrainConfig,
    *,
    device: str | None = None,
    checkpoint_path: Path | None = None,
) -> dict[str, Any]:
    """Two-stage transfer learning with fixed epoch budget (no outer-fold ES)."""

    import torch

    _seed_everything(config)
    if device is None:
        device = "cuda" if torch.cuda.is_available() else "cpu"

    # Reject uncertain/excluded from training refs.
    clean_refs = [r for r in train_refs if r.label in TRAINING_LABELS]
    if len(clean_refs) != len(train_refs):
        rejected = len(train_refs) - len(clean_refs)
        raise ValueError(f"Rejected {rejected} non-training labels from train refs")

    model = build_model(pretrained=True)
    freeze_features(model)
    model.to(device)

    targets = _targets_tensor(clean_refs).to(device)
    pos_weight = compute_pos_weights(targets)
    criterion = build_criterion(
        config.loss,
        pos_weight=pos_weight,
        handwriting_fn_multiplier=config.handwriting_fn_multiplier,
        focal_alpha=config.focal_alpha,
        focal_gamma=config.focal_gamma,
    )

    train_ds = CropDataset(clean_refs, train=True, config=config, seed=config.random_seed)
    loader = _make_loader(train_ds, config, shuffle=True, refs=clean_refs)

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

    _run_epochs(config.stage1_epochs, config.stage1_lr)
    unfreeze_final_blocks(model, n_blocks=3)
    _run_epochs(config.stage2_epochs, config.stage2_lr)

    hard_count = sum(1 for r in clean_refs if is_hard_project_example(r))

    if checkpoint_path is not None:
        checkpoint_path.parent.mkdir(parents=True, exist_ok=True)
        torch.save(
            {
                "model_state_dict": model.state_dict(),
                "config": config.to_dict(),
                "risk_order": list(RISK_ORDER),
                "pos_weight": pos_weight.detach().cpu().tolist(),
            },
            checkpoint_path,
        )

    return {
        "model": model,
        "device": device,
        "history": history,
        "pos_weight": pos_weight.detach().cpu().tolist(),
        "parameter_counts": parameter_counts(model),
        "train_counts": {
            lab: sum(1 for r in clean_refs if r.label == lab) for lab in TRAINING_LABELS
        },
        "project_handwriting_count": sum(
            1 for r in clean_refs if r.project_handwriting and not r.public
        ),
        "public_handwriting_count": sum(1 for r in clean_refs if r.public),
        "hard_example_count": hard_count,
        "effective_examples_per_epoch": len(clean_refs),
        "loss": config.loss,
        "handwriting_fn_multiplier": config.handwriting_fn_multiplier,
    }


def predict_logits(
    model: Any,
    refs: Sequence[ExampleRef],
    *,
    device: str,
    batch_size: int = 8,
) -> list[dict[str, Any]]:
    """Run deterministic eval-preprocess inference; return per-example risk records."""

    import torch

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
            probs = torch.sigmoid(logits)
            for i, ref in enumerate(chunk):
                logit_row = logits[i].detach().cpu().numpy().astype(np.float64)
                prob_row = probs[i].detach().cpu().numpy().astype(np.float64)
                out.append(
                    {
                        "crop_id": ref.crop_id,
                        "path": ref.path,
                        "label": ref.label,
                        "source_group_id": ref.source_group_id,
                        "synthetic": ref.synthetic,
                        "public": ref.public,
                        "source_category": ref.source_category,
                        "logits": logit_row.tolist(),
                        "risk_logits": logit_row.tolist(),
                        "probabilities": prob_row.tolist(),
                        "risk_probabilities": prob_row.tolist(),
                        "p_hw": float(prob_row[0]),
                        "p_nt": float(prob_row[1]),
                    }
                )
    return out
