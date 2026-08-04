"""Phase 5 Task B: training-tooling and threshold safety tests (synthetic fixtures)."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest
from model_development.handwriting_classifier.config import (
    CANDIDATE_CONFIGS,
    CLASS_ORDER,
    ThresholdCandidate,
    TrainConfig,
)
from model_development.handwriting_classifier.dataset import (
    TrainingExample,
    class_counts,
    filter_by_groups,
    source_groups,
)
from model_development.handwriting_classifier.evaluate import confusion_matrix, summarize_oof
from model_development.handwriting_classifier.synthetic_nontext import generate_synthetic_nontext
from model_development.handwriting_classifier.thresholds import (
    evaluate_thresholds,
    route_probabilities,
    search_thresholds,
)
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


def test_class_order_fixed() -> None:
    assert CLASS_ORDER == ("printed", "handwritten", "non_text")
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
    assert {e.source_group_id for e in train} == {"g2", "g3"}
    assert not any(e.source_group_id == "g1" for e in train)


def test_class_weight_inverse_frequency() -> None:
    from model_development.handwriting_classifier.train import ExampleRef, compute_class_weights

    refs = [
        ExampleRef(path="a", label="printed", source_group_id="g"),
        ExampleRef(path="b", label="printed", source_group_id="g"),
        ExampleRef(path="c", label="handwritten", source_group_id="g"),
        ExampleRef(path="d", label="non_text", source_group_id="g"),
    ]
    weights = compute_class_weights(refs)
    assert len(weights) == 3
    # printed has highest count → lowest weight
    assert weights[0] < weights[1]
    assert weights[0] < weights[2]


def test_synthetic_nontext_deterministic(tmp_path: Path) -> None:
    a = generate_synthetic_nontext(tmp_path / "a", count=20, seed=7)
    b = generate_synthetic_nontext(tmp_path / "b", count=20, seed=7)
    assert len(a) == 20
    assert all(r["label"] == "non_text" for r in a)
    assert all(str(r["source_group_id"]).startswith("srcgrp_synth_nt_") for r in a)
    # Same seed → same pixel bytes for matching indices
    for ra, rb in zip(a, b, strict=True):
        pa = Path(str(ra["path"])).read_bytes()
        pb = Path(str(rb["path"])).read_bytes()
        assert pa == pb


def test_no_synthetic_in_project_oof_metrics() -> None:
    preds = [
        {
            "label": "printed",
            "probabilities": [0.9, 0.05, 0.05],
            "synthetic": False,
        },
        {
            "label": "non_text",
            "probabilities": [0.1, 0.1, 0.8],
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
    # Corners should be near white padding
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


def test_threshold_safety_gate_zero_hw_to_printed() -> None:
    # Perfect separation predictions
    preds = []
    for _ in range(10):
        preds.append(
            {"label": "handwritten", "probabilities": [0.05, 0.9, 0.05], "synthetic": False}
        )
    for _ in range(20):
        preds.append({"label": "printed", "probabilities": [0.9, 0.05, 0.05], "synthetic": False})
    for _ in range(5):
        preds.append({"label": "non_text", "probabilities": [0.05, 0.05, 0.9], "synthetic": False})
    cand = ThresholdCandidate(0.7, 0.6, 0.6, 0.1)
    m = evaluate_thresholds(preds, cand)
    assert m.handwritten_to_printed == 0
    assert m.nontext_to_printed == 0
    assert m.handwriting_safe_bypass_recall == 1.0
    assert m.printed_retention_recall >= 0.8
    assert m.passes_safety_gate


def test_threshold_rejects_hw_leak() -> None:
    preds = [
        {"label": "handwritten", "probabilities": [0.95, 0.03, 0.02], "synthetic": False},
        {"label": "printed", "probabilities": [0.9, 0.05, 0.05], "synthetic": False},
        {"label": "non_text", "probabilities": [0.05, 0.05, 0.9], "synthetic": False},
    ]
    cand = ThresholdCandidate(0.5, 0.9, 0.5, 0.05)
    m = evaluate_thresholds(preds, cand)
    assert m.handwritten_to_printed >= 1
    assert not m.passes_safety_gate


def test_anti_trivial_all_uncertain() -> None:
    # High thresholds force uncertain → printed retention fails
    preds = []
    for _ in range(20):
        preds.append({"label": "printed", "probabilities": [0.5, 0.3, 0.2], "synthetic": False})
    for _ in range(10):
        preds.append({"label": "handwritten", "probabilities": [0.2, 0.5, 0.3], "synthetic": False})
    for _ in range(5):
        preds.append({"label": "non_text", "probabilities": [0.2, 0.2, 0.6], "synthetic": False})
    cand = ThresholdCandidate(0.99, 0.99, 0.99, 0.5)
    m = evaluate_thresholds(preds, cand)
    assert m.printed_retention_recall < 0.8
    assert not m.passes_safety_gate


def test_bounded_threshold_search_lexicographic() -> None:
    preds = []
    for _ in range(15):
        preds.append({"label": "handwritten", "probabilities": [0.1, 0.8, 0.1], "synthetic": False})
    for _ in range(40):
        preds.append({"label": "printed", "probabilities": [0.85, 0.1, 0.05], "synthetic": False})
    for _ in range(8):
        preds.append({"label": "non_text", "probabilities": [0.1, 0.1, 0.8], "synthetic": False})
    selected, top = search_thresholds(preds)
    assert selected is not None
    assert selected.passes_safety_gate
    assert selected.handwritten_to_printed == 0
    assert len(top) <= 20


def test_route_uses_existing_decision_service() -> None:
    outcome = route_probabilities([0.9, 0.05, 0.05], ThresholdCandidate(0.8, 0.7, 0.7, 0.1))
    assert outcome == "printed"
    outcome_u = route_probabilities([0.4, 0.35, 0.25], ThresholdCandidate(0.85, 0.7, 0.8, 0.1))
    assert outcome_u == "uncertain"


def test_config_hash_stable() -> None:
    a = TrainConfig(name="weighted_default_aug")
    b = TrainConfig(name="weighted_default_aug")
    assert a.config_hash() == b.config_hash()
    c = TrainConfig(name="weighted_default_aug", stage1_epochs=99)
    assert a.config_hash() != c.config_hash()


def test_uncertain_excluded_from_class_counts() -> None:
    examples = [_ex("a", "g", "printed"), _ex("b", "g", "handwritten"), _ex("c", "g", "non_text")]
    counts = class_counts(examples)
    assert set(counts) == set(CLASS_ORDER)
    assert "uncertain" not in counts


@pytest.mark.skipif(
    __import__("importlib").util.find_spec("torch") is None,
    reason="torch not installed (model-dev group)",
)
def test_model_three_logits_and_class_order() -> None:
    torch = pytest.importorskip("torch")
    from model_development.handwriting_classifier.model import build_model, parameter_counts

    model = build_model(pretrained=False)
    x = torch.zeros(2, 3, 224, 224)
    y = model(x)
    assert tuple(y.shape) == (2, 3)
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


def test_confusion_matrix_labels() -> None:
    preds = [
        {"label": "printed", "probabilities": [0.9, 0.05, 0.05], "synthetic": False},
        {"label": "handwritten", "probabilities": [0.1, 0.8, 0.1], "synthetic": False},
    ]
    cm = confusion_matrix(preds)
    assert cm["labels"] == list(CLASS_ORDER)
    assert cm["matrix"][0][0] == 1
    assert cm["matrix"][1][1] == 1
