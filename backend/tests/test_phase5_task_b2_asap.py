"""Phase 5 Task B2: Handwritten ASAP prepare / isolation / slice-gate tests."""

from __future__ import annotations

import zipfile
from pathlib import Path

import pytest
from model_development.handwriting_classifier.config import CANDIDATE_CONFIGS, ThresholdCandidate
from model_development.handwriting_classifier.public_data.download import (
    _assert_allowed_url,
    md5_file,
    sha256_file,
)
from model_development.handwriting_classifier.public_data.extract import (
    UnsafeArchiveError,
    safe_extract_zip,
)
from model_development.handwriting_classifier.public_data.licence import (
    ARCHIVE_FILENAME,
    LICENCE_ID,
    OFFICIAL_MD5,
    require_cc_by_4_0,
)
from model_development.handwriting_classifier.public_data.refs import load_asap_handwriting_refs
from model_development.handwriting_classifier.public_data.sample import (
    build_subset,
    frame_handwriting_crop,
)
from model_development.handwriting_classifier.thresholds import evaluate_thresholds
from PIL import Image

ROOT = Path(__file__).resolve().parents[2]


def test_candidate_configs_are_dual_risk_asap_mixtures() -> None:
    names = {c.name for c in CANDIDATE_CONFIGS}
    assert names == {
        "dual_risk_weighted_bce",
        "dual_risk_asymmetric_bce",
        "dual_risk_focal",
    }
    assert all(c.public_asap_variant == "medium" for c in CANDIDATE_CONFIGS)
    assert len(CANDIDATE_CONFIGS) <= 3


def test_no_nist_or_emnist_in_training_package() -> None:
    train_pkg = ROOT / "model_development" / "handwriting_classifier"
    for path in train_pkg.rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        assert "from openai" not in text
        assert "import cv2" not in text
        lower = text.lower()
        assert "emnist" not in lower
        assert "nist sd19" not in lower
        assert "special database 19" not in lower
        assert "download.pytorch.org/datasets" not in lower


def test_asap_download_url_allowlist() -> None:
    _assert_allowed_url("https://zenodo.org/api/records/8088866/files/x/content")
    with pytest.raises(ValueError):
        _assert_allowed_url("http://zenodo.org/api/records/8088866/files/x/content")
    with pytest.raises(ValueError):
        _assert_allowed_url("https://evil.example/nist.zip")


def test_require_cc_by_4_0() -> None:
    require_cc_by_4_0("cc-by-4.0")
    with pytest.raises(RuntimeError, match="BLOCKED BY LICENSING"):
        require_cc_by_4_0("cc-by-nc-4.0")


def test_zip_traversal_rejected(tmp_path: Path) -> None:
    archive = tmp_path / "bad.zip"
    with zipfile.ZipFile(archive, "w") as zf:
        zf.writestr("../escape.png", b"not-an-image")
    with pytest.raises(UnsafeArchiveError):
        safe_extract_zip(archive, tmp_path / "out")


def test_frame_and_subset_deterministic(tmp_path: Path) -> None:
    extract = tmp_path / "extract" / "Prompt_3"
    extract.mkdir(parents=True)
    for i in range(5):
        Image.new("RGB", (200, 80), color=(10 + i, 20, 30)).save(extract / f"ans_{i}.png")
    # duplicate content
    Image.new("RGB", (200, 80), color=(10, 20, 30)).save(extract / "dup.png")
    prepared = tmp_path / "prepared"
    a = build_subset(tmp_path / "extract", prepared, seed=42, light_cap=3)
    b = build_subset(tmp_path / "extract", tmp_path / "prepared2", seed=42, light_cap=3)
    assert a["selected_count"] == b["selected_count"]
    assert a["subset_manifest_sha256"] == b["subset_manifest_sha256"]
    assert a["exact_duplicates"] >= 1
    assert a["light_count"] == 3
    # All labelled handwritten only
    assert all(r["label"] == "handwritten" for r in a["selected"])


def test_load_asap_refs_train_only(tmp_path: Path) -> None:
    extract = tmp_path / "extract" / "Prompt_4"
    extract.mkdir(parents=True)
    Image.new("RGB", (120, 60), color=(0, 0, 0)).save(extract / "a.png")
    prepared = tmp_path / "prepared"
    build_subset(tmp_path / "extract", prepared, seed=1)
    refs = load_asap_handwriting_refs(tmp_path, variant="medium")
    assert len(refs) >= 1
    assert all(r.label == "handwritten" for r in refs)
    assert all(r.public for r in refs)
    assert all(not r.project_handwriting for r in refs)


def test_checksum_helpers(tmp_path: Path) -> None:
    p = tmp_path / "f.bin"
    p.write_bytes(b"abc")
    assert md5_file(p) == "900150983cd24fb0d6963f7d28e17f72"
    assert len(sha256_file(p)) == 64


def test_slice_gates_fail_on_cursive_printed() -> None:
    preds = [
        {
            "label": "handwritten",
            "probabilities": [0.05, 0.05],
            "risk_probabilities": [0.05, 0.05],
            "synthetic": False,
            "source_category": "cursive",
        },
        {
            "label": "handwritten",
            "probabilities": [0.95, 0.05],
            "risk_probabilities": [0.95, 0.05],
            "synthetic": False,
            "source_category": "signature",
        },
        {
            "label": "printed",
            "probabilities": [0.05, 0.05],
            "risk_probabilities": [0.05, 0.05],
            "synthetic": False,
        },
        {
            "label": "non_text",
            "probabilities": [0.05, 0.95],
            "risk_probabilities": [0.05, 0.95],
            "synthetic": False,
        },
    ]
    # Low HW accept / high safe-low would not apply; cursive with both risks low → printed
    m = evaluate_thresholds(preds, ThresholdCandidate(0.70, 0.20, 0.70, 0.20))
    assert m.handwritten_to_printed >= 1
    assert m.passes_slice_gates is False
    assert m.passes_safety_gate is False


def test_slice_gates_fail_on_signature_non_text() -> None:
    preds = [
        {
            "label": "handwritten",
            "probabilities": [0.05, 0.95],
            "risk_probabilities": [0.05, 0.95],
            "synthetic": False,
            "source_category": "signature",
        },
        {
            "label": "handwritten",
            "probabilities": [0.95, 0.05],
            "risk_probabilities": [0.95, 0.05],
            "synthetic": False,
            "source_category": "cursive",
        },
        {
            "label": "printed",
            "probabilities": [0.05, 0.05],
            "risk_probabilities": [0.05, 0.05],
            "synthetic": False,
        },
        {
            "label": "non_text",
            "probabilities": [0.05, 0.95],
            "risk_probabilities": [0.05, 0.95],
            "synthetic": False,
        },
    ]
    m = evaluate_thresholds(preds, ThresholdCandidate(0.70, 0.20, 0.70, 0.20))
    assert m.slice_gates["signature_routed_non_text"] == 1
    assert m.passes_slice_gates is False


def test_public_flag_excluded_from_safety_eval() -> None:
    preds = [
        {
            "label": "handwritten",
            "probabilities": [0.05, 0.05],
            "risk_probabilities": [0.05, 0.05],
            "synthetic": False,
            "public": True,
            "source_category": "cursive",
        },
        {
            "label": "handwritten",
            "probabilities": [0.95, 0.05],
            "risk_probabilities": [0.95, 0.05],
            "synthetic": False,
            "public": False,
            "source_category": "cursive",
        },
        {
            "label": "printed",
            "probabilities": [0.05, 0.05],
            "risk_probabilities": [0.05, 0.05],
            "synthetic": False,
        },
        {
            "label": "non_text",
            "probabilities": [0.05, 0.95],
            "risk_probabilities": [0.05, 0.95],
            "synthetic": False,
        },
    ]
    m = evaluate_thresholds(preds, ThresholdCandidate(0.70, 0.20, 0.70, 0.20))
    assert m.handwritten_to_printed == 0
    assert m.passes_slice_gates
    assert m.passes_safety_gate


def test_fastapi_does_not_import_asap_prepare() -> None:
    offenders = []
    for path in (ROOT / "backend" / "app").rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        if "public_data" in text or "prepare_asap" in text or "handwritten_asap" in text:
            offenders.append(str(path.relative_to(ROOT)))
    assert offenders == []


def test_gitignore_covers_asap_data() -> None:
    gi = (ROOT / ".gitignore").read_text(encoding="utf-8")
    assert "model_development/.data/" in gi


def test_official_constants() -> None:
    assert ARCHIVE_FILENAME == "Handwritten-ASAP-SAS-V1.0.zip"
    assert OFFICIAL_MD5 == "d365ea3ca8afc19d4758a22daa2e1ea2"
    assert LICENCE_ID == "cc-by-4.0"


def test_frame_crop_output_size() -> None:
    img = Image.new("RGB", (1960, 1575), color=(40, 40, 40))
    out = frame_handwriting_crop(img, target_long_edge=512)
    assert out.size == (512, 512)
