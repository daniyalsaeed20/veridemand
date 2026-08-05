"""Phase 5 Task B4: route-first targets, masking, losses, thresholds, and safety tests."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest
from model_development.handwriting_classifier import ROUTE_ORDER, TRAINING_LABELS
from model_development.handwriting_classifier.config import (
    CANDIDATE_CONFIGS,
    ThresholdCandidate,
    TrainConfig,
    default_threshold_grid,
    route_target_and_mask,
)
from model_development.handwriting_classifier.dataset import (
    TrainingExample,
    class_counts,
    filter_by_groups,
    source_groups,
)
from model_development.handwriting_classifier.evaluate import summarize_oof
from model_development.handwriting_classifier.losses import (
    compute_pos_weights,
    route_first_combined_loss,
)
from model_development.handwriting_classifier.synthetic_nontext import generate_synthetic_nontext
from model_development.handwriting_classifier.thresholds import (
    evaluate_thresholds,
    route_probabilities,
    search_thresholds,
)
from model_development.handwriting_classifier.transforms import (
    letterbox_rgb,
    runtime_preprocess,
)
from PIL import Image

from backend.app.extraction.handwriting_router.routing import (
    RoutingThresholds,
    decide_routing_outcome,
)


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


def test_route_order_and_targets() -> None:
    assert ROUTE_ORDER == ("vision_required", "handwriting_present")
    assert route_target_and_mask("printed") == (0.0, 0.0, 1.0)
    assert route_target_and_mask("handwritten") == (1.0, 1.0, 1.0)
    assert route_target_and_mask("uncertain") == (1.0, 0.0, 0.0)
    assert route_target_and_mask("non_text") == (1.0, 0.0, 1.0)


def test_public_and_synthetic_targets() -> None:
    # ASAP handwriting and synthetic non-text use the same human labels.
    assert route_target_and_mask("handwritten")[:2] == (1.0, 1.0)
    assert route_target_and_mask("non_text")[:2] == (1.0, 0.0)


def test_candidate_configs_are_route_first() -> None:
    names = {c.name for c in CANDIDATE_CONFIGS}
    assert names == {
        "route_first_weighted_bce",
        "route_first_asymmetric_bce",
        "route_first_focal",
    }
    assert len(CANDIDATE_CONFIGS) <= 3
    assert all(c.public_asap_variant == "medium" for c in CANDIDATE_CONFIGS)
    losses = {c.loss for c in CANDIDATE_CONFIGS}
    assert losses == {"weighted_bce", "asymmetric_bce", "focal"}
    assert all(c.route_loss_weight >= c.handwriting_loss_weight for c in CANDIDATE_CONFIGS)


def test_source_group_isolation() -> None:
    examples = [
        _ex("c1", "g1", "printed"),
        _ex("c2", "g1", "handwritten"),
        _ex("c3", "g2", "uncertain"),
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


def test_letterbox_and_preprocess() -> None:
    img = Image.new("RGB", (200, 50), color=(10, 20, 30))
    canvas = letterbox_rgb(img, size=224, padding_value=255)
    assert canvas.size == (224, 224)
    t = runtime_preprocess(img)
    assert t.shape == (1, 3, 224, 224)
    assert t.dtype == np.float32


@pytest.mark.skipif(
    __import__("importlib").util.find_spec("torch") is None,
    reason="torch not installed (model-dev group)",
)
def test_uncertain_masking_stable() -> None:
    import torch

    logits = torch.tensor([[2.0, 0.5], [2.0, -1.0], [-2.0, -2.0]], requires_grad=True)
    targets = torch.tensor([[1.0, 0.0], [1.0, 1.0], [0.0, 0.0]])
    # First row uncertain (mask 0); second handwritten; third printed.
    mask = torch.tensor([0.0, 1.0, 1.0])
    pos = compute_pos_weights(targets, mask)
    loss = route_first_combined_loss(
        logits,
        targets,
        mask,
        loss_name="weighted_bce",
        pos_weight=pos,
        route_loss_weight=1.0,
        handwriting_loss_weight=0.5,
    )
    assert torch.isfinite(loss)
    loss.backward()
    assert logits.grad is not None
    assert torch.all(torch.isfinite(logits.grad))
    # Fully masked HW batch remains stable.
    mask_all = torch.zeros(3)
    loss2 = route_first_combined_loss(
        logits.detach().clone().requires_grad_(True),
        targets,
        mask_all,
        loss_name="weighted_bce",
        pos_weight=pos,
    )
    assert torch.isfinite(loss2)


@pytest.mark.skipif(
    __import__("importlib").util.find_spec("torch") is None,
    reason="torch not installed",
)
def test_model_two_route_logits() -> None:
    torch = pytest.importorskip("torch")
    from model_development.handwriting_classifier.model import build_model

    model = build_model(pretrained=False)
    y = model(torch.zeros(2, 3, 224, 224))
    assert tuple(y.shape) == (2, 2)


def test_threshold_ordering_enforced() -> None:
    grid = default_threshold_grid()
    assert all(c.is_ordered() for c in grid)
    assert len(grid) > 50
    bad = ThresholdCandidate(0.70, 0.20, 0.70)
    assert not bad.is_ordered()


def _route_preds_perfect() -> list[dict[str, object]]:
    preds: list[dict[str, object]] = []
    for _ in range(10):
        preds.append(
            {
                "label": "handwritten",
                "probabilities": [0.95, 0.92],
                "route_probabilities": [0.95, 0.92],
                "synthetic": False,
                "source_category": "cursive",
            }
        )
    for _ in range(5):
        preds.append(
            {
                "label": "handwritten",
                "probabilities": [0.92, 0.88],
                "route_probabilities": [0.92, 0.88],
                "synthetic": False,
                "source_category": "signature",
            }
        )
    for _ in range(40):
        preds.append(
            {
                "label": "printed",
                "probabilities": [0.05, 0.05],
                "route_probabilities": [0.05, 0.05],
                "synthetic": False,
            }
        )
    for _ in range(8):
        preds.append(
            {
                "label": "non_text",
                "probabilities": [0.90, 0.10],
                "route_probabilities": [0.90, 0.10],
                "synthetic": False,
            }
        )
    for _ in range(6):
        preds.append(
            {
                "label": "uncertain",
                "probabilities": [0.85, 0.40],
                "route_probabilities": [0.85, 0.40],
                "synthetic": False,
            }
        )
    return preds


def test_threshold_safety_gates_pass_on_perfect_separation() -> None:
    cand = ThresholdCandidate(0.20, 0.70, 0.70)
    m = evaluate_thresholds(_route_preds_perfect(), cand)
    assert m.handwritten_to_printed == 0
    assert m.uncertain_to_printed == 0
    assert m.nontext_to_printed == 0
    assert m.handwriting_safe_bypass_recall == 1.0
    assert m.uncertain_safe_bypass_recall == 1.0
    assert m.printed_retention_recall >= 0.8
    assert m.passes_slice_gates
    assert m.passes_safety_gate


def test_uncertain_to_printed_fails_gate() -> None:
    preds = [
        {
            "label": "uncertain",
            "probabilities": [0.05, 0.05],
            "route_probabilities": [0.05, 0.05],
            "synthetic": False,
        },
        {
            "label": "printed",
            "probabilities": [0.05, 0.05],
            "route_probabilities": [0.05, 0.05],
            "synthetic": False,
        },
        {
            "label": "handwritten",
            "probabilities": [0.95, 0.90],
            "route_probabilities": [0.95, 0.90],
            "synthetic": False,
            "source_category": "cursive",
        },
    ]
    m = evaluate_thresholds(preds, ThresholdCandidate(0.20, 0.70, 0.70))
    assert m.uncertain_to_printed >= 1
    assert not m.passes_safety_gate


def test_anti_all_uncertain_printed_retention() -> None:
    preds = []
    for _ in range(20):
        preds.append(
            {
                "label": "printed",
                "probabilities": [0.5, 0.1],
                "route_probabilities": [0.5, 0.1],
                "synthetic": False,
            }
        )
    for _ in range(10):
        preds.append(
            {
                "label": "handwritten",
                "probabilities": [0.5, 0.1],
                "route_probabilities": [0.5, 0.1],
                "synthetic": False,
            }
        )
    m = evaluate_thresholds(preds, ThresholdCandidate(0.10, 0.90, 0.90))
    assert m.printed_retention_recall < 0.8
    assert not m.passes_safety_gate


def test_bounded_threshold_search_finds_safe_set() -> None:
    selected, top = search_thresholds(_route_preds_perfect())
    assert selected is not None
    assert selected.passes_safety_gate
    assert selected.handwritten_to_printed == 0
    assert selected.uncertain_to_printed == 0
    assert selected.nontext_to_printed == 0
    assert len(top) <= 20


def test_route_first_decision_policy() -> None:
    cand = ThresholdCandidate(0.20, 0.70, 0.70)
    assert route_probabilities([0.05, 0.05], cand) == "printed"
    assert route_probabilities([0.90, 0.85], cand) == "handwritten"
    assert route_probabilities([0.90, 0.20], cand) == "uncertain"  # route high, HW low
    assert route_probabilities([0.40, 0.90], cand) == "uncertain"  # grey zone
    # Model never emits non_text.
    assert route_probabilities([0.90, 0.10], cand) != "non_text"


def test_decide_routing_invalid_and_nan() -> None:
    thr = RoutingThresholds(0.20, 0.70, 0.70)
    d = decide_routing_outcome([float("nan"), 0.1], thr)
    assert d.outcome.value == "uncertain"
    d2 = decide_routing_outcome([0.5], thr)
    assert d2.outcome.value == "uncertain"
    d3 = decide_routing_outcome([1.5, 0.1], thr)
    assert d3.outcome.value == "uncertain"


def test_printed_only_below_safe_threshold() -> None:
    thr = RoutingThresholds(0.20, 0.70, 0.70)
    d = decide_routing_outcome([0.21, 0.0], thr)
    assert d.outcome.value == "uncertain"
    d2 = decide_routing_outcome([0.20, 0.0], thr)
    assert d2.outcome.value == "printed"


def test_public_excluded_from_gates() -> None:
    preds = [
        {
            "label": "handwritten",
            "probabilities": [0.05, 0.05],
            "route_probabilities": [0.05, 0.05],
            "synthetic": False,
            "public": True,
            "source_category": "cursive",
        },
        {
            "label": "handwritten",
            "probabilities": [0.95, 0.90],
            "route_probabilities": [0.95, 0.90],
            "synthetic": False,
            "public": False,
            "source_category": "cursive",
        },
        {
            "label": "printed",
            "probabilities": [0.05, 0.05],
            "route_probabilities": [0.05, 0.05],
            "synthetic": False,
        },
        {
            "label": "non_text",
            "probabilities": [0.90, 0.10],
            "route_probabilities": [0.90, 0.10],
            "synthetic": False,
        },
        {
            "label": "uncertain",
            "probabilities": [0.85, 0.40],
            "route_probabilities": [0.85, 0.40],
            "synthetic": False,
        },
    ]
    m = evaluate_thresholds(preds, ThresholdCandidate(0.20, 0.70, 0.70))
    assert m.handwritten_to_printed == 0
    assert m.uncertain_to_printed == 0
    assert m.passes_safety_gate


def test_config_hash_stable() -> None:
    a = TrainConfig(name="route_first_weighted_bce", loss="weighted_bce")
    b = TrainConfig(name="route_first_weighted_bce", loss="weighted_bce")
    assert a.config_hash() == b.config_hash()
    c = TrainConfig(name="route_first_weighted_bce", loss="focal")
    assert a.config_hash() != c.config_hash()


def test_uncertain_in_training_counts() -> None:
    examples = [
        _ex("a", "g", "printed"),
        _ex("b", "g", "handwritten"),
        _ex("c", "g", "uncertain"),
        _ex("d", "g", "non_text"),
    ]
    counts = class_counts(examples)
    assert set(counts) == set(TRAINING_LABELS)
    assert counts["uncertain"] == 1


def test_oof_summary_excludes_synthetic() -> None:
    preds = [
        {
            "label": "printed",
            "probabilities": [0.05, 0.05],
            "route_probabilities": [0.05, 0.05],
            "synthetic": False,
        },
        {
            "label": "non_text",
            "probabilities": [0.9, 0.1],
            "route_probabilities": [0.9, 0.1],
            "synthetic": True,
        },
    ]
    summary = summarize_oof(preds)
    assert summary["n_examples"] == 1
    assert "route_head_metrics" in summary
