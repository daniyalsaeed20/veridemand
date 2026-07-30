"""Phase 5 Task 3A dataset schema and padding tests."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from backend.app.contracts.geometry import NormalisedBoundingBox
from backend.app.datasets.phase5.constants import CROP_PADDING_VERSION, HUMAN_LABELS
from backend.app.datasets.phase5.ids import new_crop_id, new_source_group_id
from backend.app.datasets.phase5.padding import apply_crop_padding
from backend.app.datasets.phase5.schemas import CropRecord, ReviewEvent, SourceRecord


def test_human_labels_enum() -> None:
    assert {"printed", "handwritten", "uncertain", "non_text"} == HUMAN_LABELS


def test_padding_clamps_to_page() -> None:
    bbox = NormalisedBoundingBox(x=0.0, y=0.0, width=0.1, height=0.1)
    crop, applied = apply_crop_padding(bbox)
    assert applied.policy_version == CROP_PADDING_VERSION
    assert applied.clamped is True
    assert crop.x >= 0.0
    assert crop.y >= 0.0
    assert crop.x + crop.width <= 1.0 + 1e-9
    assert crop.y + crop.height <= 1.0 + 1e-9


def test_crop_record_forbids_unknown_fields() -> None:
    bbox = NormalisedBoundingBox(x=0.1, y=0.1, width=0.2, height=0.2)
    crop_bbox, applied = apply_crop_padding(bbox)
    with pytest.raises(ValidationError):
        CropRecord.model_validate(
            {
                "crop_id": new_crop_id(),
                "source_group_id": new_source_group_id(),
                "document_id": "doc_abcdefghijklmnop",
                "page_id": "page_abcdefghijklmnop",
                "page_index": 0,
                "candidate_source": "manual_region",
                "source_bbox": bbox.model_dump(),
                "crop_bbox": crop_bbox.model_dump(),
                "applied_padding": applied.model_dump(),
                "crop_relpath": "crops/x.png",
                "sha256": "a" * 64,
                "perceptual_hash": "b" * 16,
                "width_px": 10,
                "height_px": 10,
                "created_at": datetime.now(UTC).isoformat(),
                "ocr_text": "leak",
            }
        )


def test_review_event_requires_known_label() -> None:
    with pytest.raises(ValidationError):
        ReviewEvent.model_validate(
            {
                "review_id": "review_abcdefghijklmn",
                "crop_id": new_crop_id(),
                "crop_sha256": "a" * 64,
                "reviewer_id": "rev1",
                "role": "primary",
                "action": "label",
                "label": "signature",
                "created_at": datetime.now(UTC).isoformat(),
            }
        )


def test_source_record_roundtrip() -> None:
    rec = SourceRecord(
        source_group_id=new_source_group_id(),
        document_id="doc_abcdefghijklmnop",
        page_id="page_abcdefghijklmnop",
        page_index=0,
        created_at=datetime.now(UTC),
    )
    assert SourceRecord.model_validate_json(rec.model_dump_json()).page_index == 0
