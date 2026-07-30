"""Resolve human review events into training-eligible labels."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import cast

from backend.app.datasets.phase5.constants import MODEL_TRAINING_LABELS
from backend.app.datasets.phase5.jsonl_io import read_jsonl, write_jsonl_atomic
from backend.app.datasets.phase5.paths import manifest_path
from backend.app.datasets.phase5.schemas import (
    CropRecord,
    ExclusionRecord,
    HumanLabel,
    ResolutionStatus,
    ResolvedLabelRecord,
    ReviewEvent,
)


def _now() -> datetime:
    return datetime.now(UTC)


def resolve_events_for_crop(
    crop: CropRecord,
    events: list[ReviewEvent],
    exclusions: set[str],
) -> ResolvedLabelRecord:
    """Derive resolution for one crop from append-only review events."""

    crop_events = [e for e in events if e.crop_id == crop.crop_id]
    # Hash mismatch invalidates prior labels for this crop content.
    mismatched = [e for e in crop_events if e.crop_sha256 != crop.sha256]
    matched = [e for e in crop_events if e.crop_sha256 == crop.sha256]

    if crop.crop_id in exclusions:
        return ResolvedLabelRecord(
            crop_id=crop.crop_id,
            crop_sha256=crop.sha256,
            status="excluded",
            label=None,
            training_eligible=False,
            source_group_id=crop.source_group_id,
            duplicate_family_id=crop.duplicate_family_id,
            resolved_at=_now(),
        )

    if mismatched and not matched:
        return ResolvedLabelRecord(
            crop_id=crop.crop_id,
            crop_sha256=crop.sha256,
            status="invalidated_hash_mismatch",
            label=None,
            training_eligible=False,
            source_group_id=crop.source_group_id,
            duplicate_family_id=crop.duplicate_family_id,
            resolved_at=_now(),
        )

    # Latest exclude action wins among matched events.
    for event in reversed(matched):
        if event.action == "exclude":
            return ResolvedLabelRecord(
                crop_id=crop.crop_id,
                crop_sha256=crop.sha256,
                status="excluded",
                label=None,
                training_eligible=False,
                source_group_id=crop.source_group_id,
                duplicate_family_id=crop.duplicate_family_id,
                resolved_at=_now(),
            )

    labels_by_role: dict[str, HumanLabel] = {}
    for event in matched:
        if event.action == "label" and event.label is not None:
            labels_by_role[event.role] = event.label

    primary = labels_by_role.get("primary")
    secondary = labels_by_role.get("secondary")
    adjudicator = labels_by_role.get("adjudicator")

    final: HumanLabel | None = None
    res_status: str

    if (
        adjudicator is not None
        and primary is not None
        and secondary is not None
        and primary != secondary
    ):
        final = adjudicator
        res_status = "adjudicated"
    elif primary is not None and secondary is not None:
        if primary == secondary:
            final = primary
            res_status = "agreed"
        else:
            final = None
            res_status = "conflict"
    elif primary is not None or secondary is not None:
        final = primary or secondary
        res_status = "single_review"
    else:
        final = None
        res_status = "unreviewed"

    # Signatures are labelled as handwritten by policy (labeler maps S→handwritten).
    training_eligible = (
        final is not None
        and final in MODEL_TRAINING_LABELS
        and res_status in {"agreed", "adjudicated"}
    )

    return ResolvedLabelRecord(
        crop_id=crop.crop_id,
        crop_sha256=crop.sha256,
        status=cast(ResolutionStatus, res_status),
        label=final,
        training_eligible=training_eligible,
        primary_label=primary,
        secondary_label=secondary,
        adjudicator_label=adjudicator,
        source_group_id=crop.source_group_id,
        duplicate_family_id=crop.duplicate_family_id,
        resolved_at=_now(),
    )


def resolve_dataset(private_root: Path) -> list[ResolvedLabelRecord]:
    crops = read_jsonl(manifest_path(private_root, "crop-manifest.jsonl"), CropRecord)
    events = read_jsonl(manifest_path(private_root, "review-events.jsonl"), ReviewEvent)
    exclusions = {
        e.crop_id
        for e in read_jsonl(manifest_path(private_root, "exclusions.jsonl"), ExclusionRecord)
    }
    resolved = [resolve_events_for_crop(c, events, exclusions) for c in crops]
    write_jsonl_atomic(manifest_path(private_root, "resolved-labels.jsonl"), resolved)
    return resolved
