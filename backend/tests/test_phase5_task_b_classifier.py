"""Phase 5 Task B historical tests retargeted to dual-risk (Task B3).

Task B three-class softmax remains a documented prototype baseline —
superseded for safety evaluation. Active assertions cover shared tooling
still used by Task B3 (LOSGO helpers, synth non-text, preprocess).
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest
from model_development.handwriting_classifier import TRAINING_LABELS
from model_development.handwriting_classifier.config import CANDIDATE_CONFIGS, TrainConfig
from model_development.handwriting_classifier.dataset import (
    TrainingExample,
    class_counts,
    filter_by_groups,
    source_groups,
)
from model_development.handwriting_classifier.evaluate import summarize_oof
from model_development.handwriting_classifier.synthetic_nontext import generate_synthetic_nontext
from model_development.handwriting_classifier.transforms import (
    letterbox_rgb,
    runtime_preprocess,
    to_nchw_normalized,
)
from PIL import Image


def _ex(crop_id: str, group: str, label: str, path: str = "/tmp/x.png") -> TrainingExample:
    return TrainingExample(
        schema_version="phase5-classifier-training-schema-v1",
        training_manifest_version="phase5-classifier-training-manifest-v1",
        crop_id=crop_id,
        crop_sha256=f"{crop_id:0<64}"[:64],
        source_group_id=group,
        label=label,  # type: ignore[arg-type]
        label_source="prototype_primary_review",
        review_status="single_review",
        crop_path_private=path,
        width=64,
        height=32,
    )


def test_training_labels_fixed() -> None:
    assert TRAINING_LABELS == ("printed", "handwritten", "non_text")
    assert len(CANDIDATE_CONFIGS) <= 3


def test_source_group_isolation() -> None:
    examples = [
        _ex("c1", "g1", "printed"),
        _ex("c2", "g1", "handwritten"),
        _ex("c3", "g2", "printed"),
        _ex("c4", "g3", "non_text"),
    ]
    groups = source_groups(examples)
    assert groups == ["g1", "g2", "g3"]
    held = filter_by_groups(examples, {"g1"})
    train = filter_by_groups(examples, set(groups) - {"g1"})
    assert {e.crop_id for e in held} == {"c1", "c2"}
    assert not any(e.source_group_id == "g1" for e in train)


def test_synthetic_nontext_deterministic(tmp_path: Path) -> None:
    a = generate_synthetic_nontext(tmp_path / "a", count=20, seed=7)
    b = generate_synthetic_nontext(tmp_path / "b", count=20, seed=7)
    assert len(a) == 20
    assert all(r["label"] == "non_text" for r in a)
    for ra, rb in zip(a, b, strict=True):
        assert Path(str(ra["path"])).read_bytes() == Path(str(rb["path"])).read_bytes()


def test_no_synthetic_in_project_oof_metrics() -> None:
    preds = [
        {
            "label": "printed",
            "probabilities": [0.05, 0.05],
            "risk_probabilities": [0.05, 0.05],
            "synthetic": False,
        },
        {
            "label": "non_text",
            "probabilities": [0.1, 0.8],
            "risk_probabilities": [0.1, 0.8],
            "synthetic": True,
        },
    ]
    summary = summarize_oof(preds)
    assert summary["n_examples"] == 1
    assert summary["class_support"]["printed"] == 1
    assert summary["class_support"]["non_text"] == 0


def test_letterbox_preserves_aspect() -> None:
    img = Image.new("RGB", (200, 50), color=(10, 20, 30))
    canvas = letterbox_rgb(img, size=224, padding_value=255)
    assert canvas.size == (224, 224)
    arr = np.asarray(canvas)
    assert int(arr[0, 0, 0]) == 255


def test_runtime_preprocess_shape_and_dtype() -> None:
    img = Image.new("RGB", (80, 120), color=(128, 128, 128))
    t = runtime_preprocess(img)
    assert t.shape == (1, 3, 224, 224)
    assert t.dtype == np.float32
    assert np.all(np.isfinite(t))


def test_runtime_preprocess_matches_manual_pipeline() -> None:
    img = Image.new("RGB", (60, 90), color=(200, 180, 160))
    a = runtime_preprocess(img)
    b = to_nchw_normalized(letterbox_rgb(img))
    assert np.allclose(a, b, atol=1e-6)


def test_config_hash_stable() -> None:
    a = TrainConfig(name="dual_risk_weighted_bce")
    b = TrainConfig(name="dual_risk_weighted_bce")
    assert a.config_hash() == b.config_hash()
    c = TrainConfig(name="dual_risk_weighted_bce", stage1_epochs=99)
    assert a.config_hash() != c.config_hash()


def test_uncertain_excluded_from_class_counts() -> None:
    examples = [_ex("a", "g", "printed"), _ex("b", "g", "handwritten"), _ex("c", "g", "non_text")]
    counts = class_counts(examples)
    assert set(counts) == set(TRAINING_LABELS)
    assert "uncertain" not in counts


@pytest.mark.skipif(
    __import__("importlib").util.find_spec("torch") is None,
    reason="torch not installed (model-dev group)",
)
def test_model_dual_risk_logits() -> None:
    torch = pytest.importorskip("torch")
    from model_development.handwriting_classifier.model import build_model, parameter_counts

    model = build_model(pretrained=False)
    x = torch.zeros(2, 3, 224, 224)
    y = model(x)
    assert tuple(y.shape) == (2, 2)
    counts = parameter_counts(model)
    assert counts["total"] > 0


@pytest.mark.skipif(
    __import__("importlib").util.find_spec("torch") is None,
    reason="torch not installed",
)
def test_augmentation_deterministic_under_seed() -> None:
    from model_development.handwriting_classifier.transforms import augment_train

    img = Image.new("RGB", (100, 40), color=(100, 100, 100))
    rng1 = np.random.default_rng(123)
    rng2 = np.random.default_rng(123)
    a = np.asarray(augment_train(img, rng1))
    b = np.asarray(augment_train(img, rng2))
    assert np.array_equal(a, b)
