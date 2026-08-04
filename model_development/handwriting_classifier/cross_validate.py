"""Leave-one-source-group-out diagnostics."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from model_development.handwriting_classifier.config import TrainConfig
from model_development.handwriting_classifier.dataset import (
    TrainingExample,
    filter_by_groups,
    source_groups,
)
from model_development.handwriting_classifier.evaluate import fold_support, summarize_oof
from model_development.handwriting_classifier.synthetic_nontext import generate_synthetic_nontext
from model_development.handwriting_classifier.train import predict_logits, to_refs, train_model


def run_losgo(
    fit_examples: list[TrainingExample],
    config: TrainConfig,
    *,
    artifacts_dir: Path,
    challenge: list[TrainingExample] | None = None,
    device: str | None = None,
    public_refs: list[Any] | None = None,
) -> dict[str, Any]:
    """Train one model per held-out project source group; aggregate OOF preds.

    ``public_refs`` (e.g. ASAP handwriting) are training-only and never enter
    held-out OOF predictions.
    """

    groups = source_groups(fit_examples)
    synth_dir = artifacts_dir / "synthetic_nontext" / config.name
    synthetic = generate_synthetic_nontext(
        synth_dir,
        count=config.synthetic_nontext_count,
        seed=config.random_seed,
    )
    public = list(public_refs or [])

    all_oof: list[dict[str, Any]] = []
    fold_reports: list[dict[str, Any]] = []

    for held in groups:
        train_groups = set(groups) - {held}
        train_ex = filter_by_groups(fit_examples, train_groups)
        held_ex = filter_by_groups(fit_examples, {held})
        train_refs = to_refs(train_ex, synthetic)
        if public:
            train_refs = list(train_refs) + list(public)
        held_refs = to_refs(held_ex, None)

        # Opaque fold id (never emit raw source_group_id into committed reports).
        fold_idx = groups.index(held)
        ckpt = artifacts_dir / "checkpoints" / config.name / f"fold_{fold_idx:02d}.pt"
        result = train_model(train_refs, config, device=device, checkpoint_path=ckpt)
        model = result["model"]
        used_device = result["device"]

        preds = predict_logits(model, held_refs, device=used_device, batch_size=config.batch_size)
        for p, ex in zip(preds, held_ex, strict=True):
            p["held_out_fold_index"] = fold_idx
            p["config_name"] = config.name
            p["width"] = ex.width
            p["height"] = ex.height
            p["source_category"] = ex.source_category
            p["public"] = False
            # Strip private path from in-memory records before any report serialization.
            p.pop("path", None)
        all_oof.extend(preds)
        fold_reports.append(
            {
                "held_out_fold_index": fold_idx,
                "held_out_support": fold_support(preds),
                "train_counts": result["train_counts"],
                "public_train_count": len(public),
                "class_weights": result["class_weights"],
                "parameter_counts": result["parameter_counts"],
                "device": used_device,
            }
        )
        del model
        del result

    # Challenge crops are never trained on; scored later with the final selected model.
    _ = challenge

    return {
        "config": config.to_dict(),
        "config_hash": config.config_hash(),
        "fold_reports": fold_reports,
        "oof_predictions": all_oof,
        "oof_summary": summarize_oof(all_oof),
        "synthetic_nontext_count": len(synthetic),
        "public_handwriting_count": len(public),
        "source_group_count": len(groups),
    }
