"""Targeted handwriting-seed queue, confirmation, verification, and aggregates.

Human-only. No OCR, no classifier, no transcription. Private manifests only.
"""

from __future__ import annotations

import hashlib
import json
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal, cast

from PIL import Image

from backend.app.contracts.geometry import NormalisedBoundingBox
from backend.app.datasets.phase5.constants import (
    COVERAGE_CORRECTION_OUTCOMES,
    HANDWRITING_SEED_CATEGORIES,
    HANDWRITING_SEED_HEURISTIC_FAMILIES,
    HANDWRITING_SEED_MAX_AREA_WARN,
    HANDWRITING_SEED_MIN_AREA_WARN,
    HANDWRITING_SEED_QUEUE_VERSION,
    HANDWRITING_SEED_REPORT_VERSION,
    HANDWRITING_SEED_SCHEMA_VERSION,
    HANDWRITING_SEED_SOURCE_TYPE,
    HANDWRITING_SEED_TARGET_REGIONS,
    PERCEPTUAL_HAMMING_WARN_THRESHOLD,
)
from backend.app.datasets.phase5.export import export_crop_from_page
from backend.app.datasets.phase5.hashes import hamming_hex, sha256_file
from backend.app.datasets.phase5.ids import (
    new_handwriting_seed_event_id,
    new_handwriting_seed_region_id,
)
from backend.app.datasets.phase5.jsonl_io import (
    append_jsonl,
    index_by,
    read_jsonl,
    write_jsonl_atomic,
)
from backend.app.datasets.phase5.paths import (
    ensure_layout,
    manifest_path,
    pages_dir,
    reports_dir,
)
from backend.app.datasets.phase5.schemas import (
    CoverageEvent,
    CoverageQueueManifest,
    CropRecord,
    DocumentRecord,
    HandwritingSeedEvent,
    HandwritingSeedQueueEntry,
    HandwritingSeedQueueManifest,
    HandwritingSeedRecord,
    ResolvedLabelRecord,
    ReviewQueueManifest,
    SourceRecord,
)

SeedCategory = Literal[
    "digits",
    "hand_printed",
    "cursive",
    "signature",
    "correction",
    "longer_note",
]
SeedCloseAction = Literal["no_usable_handwriting", "defer", "complete_page"]


def _now() -> datetime:
    return datetime.now(UTC)


def _parse_categories(categories: list[str] | None) -> list[SeedCategory]:
    out: list[SeedCategory] = []
    for cat in categories or []:
        if cat not in HANDWRITING_SEED_CATEGORIES:
            raise ValueError(f"Unknown handwriting seed category: {cat}")
        out.append(cast(SeedCategory, cat))
    return out


def reviewer_id_ok(reviewer_id: str) -> bool:
    return (
        bool(reviewer_id)
        and reviewer_id.startswith("handwriting_reviewer_")
        and len(reviewer_id) <= 64
    )


def geometry_warnings(bbox: NormalisedBoundingBox) -> list[str]:
    area = float(bbox.width) * float(bbox.height)
    warnings: list[str] = []
    if area < HANDWRITING_SEED_MIN_AREA_WARN:
        warnings.append("unusually_small_region")
    if area > HANDWRITING_SEED_MAX_AREA_WARN:
        warnings.append("unusually_broad_region")
    return warnings


def page_render_sha256(private_root: Path, opaque_page_reference: str) -> str | None:
    path = pages_dir(private_root) / f"{opaque_page_reference}.png"
    if not path.is_file():
        return None
    return sha256_file(path)


def _family_for_page(
    *,
    page_id: str,
    sources: dict[str, SourceRecord],
    documents: dict[str, DocumentRecord],
) -> str:
    src = sources.get(page_id)
    if src and src.source_family:
        return str(src.source_family)
    if src:
        doc = documents.get(src.document_id)
        if doc:
            return str(doc.source_family)
    return "other"


def _uncertain_pages(private_root: Path) -> dict[str, int]:
    """Map page_id → count of prototype-uncertain crops (do not reinterpret labels)."""

    crops = index_by(
        read_jsonl(manifest_path(private_root, "crop-manifest.jsonl"), CropRecord),
        lambda c: c.crop_id,
    )
    resolved = {
        r.crop_id: r
        for r in read_jsonl(
            manifest_path(private_root, "resolved-labels.jsonl"), ResolvedLabelRecord
        )
    }
    queues = read_jsonl(
        manifest_path(private_root, "prototype-primary-queue.jsonl"), ReviewQueueManifest
    )
    prototype_ids: set[str] = set()
    if queues:
        for entry in queues[-1].entries:
            prototype_ids.add(entry.crop_id)
    counts: Counter[str] = Counter()
    for crop_id in prototype_ids:
        res = resolved.get(crop_id)
        crop = crops.get(crop_id)
        if res is None or crop is None:
            continue
        if res.label == "uncertain":
            counts[crop.page_id] += 1
    return dict(counts)


def _coverage_worklist_pages(private_root: Path) -> set[str]:
    path = reports_dir(private_root) / "coverage-correction-worklist.jsonl"
    pages: set[str] = set()
    if not path.is_file():
        # Fall back to current coverage issue outcomes.
        events = read_jsonl(manifest_path(private_root, "coverage-events.jsonl"), CoverageEvent)
        current: dict[str, CoverageEvent] = {}
        for event in events:
            if event.action == "reopen":
                current.pop(event.opaque_page_reference, None)
            elif event.action == "resolve" and event.outcome:
                current[event.opaque_page_reference] = event
        for page, event in current.items():
            if event.outcome in COVERAGE_CORRECTION_OUTCOMES:
                pages.add(page)
        return pages
    for line in path.read_text(encoding="utf-8").splitlines():
        text = line.strip()
        if not text:
            continue
        row = json.loads(text)
        ref = row.get("opaque_page_reference")
        if isinstance(ref, str):
            pages.add(ref)
    return pages


def build_handwriting_seed_queue(private_root: Path) -> dict[str, Any]:
    """Build deterministic targeted page queue from metadata only (no model)."""

    ensure_layout(private_root)
    sources = {
        s.page_id: s
        for s in read_jsonl(manifest_path(private_root, "source-manifest.jsonl"), SourceRecord)
    }
    documents = {
        d.document_id: d
        for d in read_jsonl(manifest_path(private_root, "document-manifest.jsonl"), DocumentRecord)
    }
    crops = read_jsonl(manifest_path(private_root, "crop-manifest.jsonl"), CropRecord)
    crops_by_page: dict[str, list[CropRecord]] = {}
    for crop in crops:
        crops_by_page.setdefault(crop.page_id, []).append(crop)

    uncertain = _uncertain_pages(private_root)
    coverage_pages = _coverage_worklist_pages(private_root)

    coverage_queues = read_jsonl(
        manifest_path(private_root, "coverage-queue.jsonl"), CoverageQueueManifest
    )
    coverage_priority: dict[str, tuple[int, list[str]]] = {}
    if coverage_queues:
        for entry in coverage_queues[-1].entries:
            coverage_priority[entry.opaque_page_reference] = (
                entry.priority_score,
                list(entry.priority_reasons),
            )

    pages_dir_path = pages_dir(private_root)
    eligible_pages = sorted(
        p.name.replace(".png", "")
        for p in pages_dir_path.glob("*.png")
        if (pages_dir_path / f"{p.name.replace('.png', '')}.png").is_file()
    )

    scored: list[tuple[int, str, list[str]]] = []
    for page_id in eligible_pages:
        src = sources.get(page_id)
        if src is None:
            continue
        family = _family_for_page(page_id=page_id, sources=sources, documents=documents)
        reasons: list[str] = []
        score = 0
        if page_id in uncertain:
            score += 1000 + min(uncertain[page_id], 50)
            reasons.append("uncertain_prototype_crop_page")
        if page_id in coverage_pages:
            score += 800
            reasons.append("coverage_worklist")
        if family == "police_form":
            score += 600
            reasons.append("police_form")
        cov_score, cov_reasons = coverage_priority.get(page_id, (0, []))
        heuristic_hit = False
        if family in HANDWRITING_SEED_HEURISTIC_FAMILIES:
            for reason in cov_reasons:
                if reason in {
                    "low_crop_count",
                    "high_crop_density",
                    "zero_crops",
                    "skipped_block_gaps",
                    "medical_form",
                    "image_document",
                    "police_form",
                }:
                    heuristic_hit = True
                    reasons.append(f"heuristic:{reason}")
            if family == "medical_form" and cov_score >= 80:
                heuristic_hit = True
                if "heuristic:medical_form" not in reasons:
                    reasons.append("heuristic:medical_form")
        if heuristic_hit:
            score += 200 + min(cov_score, 100)
        # Do not auto-add billing/insurance-only pages unless already selected above.
        if score <= 0:
            continue
        scored.append((score, page_id, sorted(set(reasons))))

    scored.sort(key=lambda t: (-t[0], t[1]))
    entries: list[HandwritingSeedQueueEntry] = []
    for idx, (score, page_id, reasons) in enumerate(scored):
        src = sources[page_id]
        entries.append(
            HandwritingSeedQueueEntry(
                opaque_page_reference=page_id,
                opaque_document_reference=src.document_id,
                source_group_id=src.source_group_id,
                queue_index=idx,
                priority_score=score,
                priority_reasons=reasons,
                crop_count=len(crops_by_page.get(page_id, [])),
                uncertain_crop_count=uncertain.get(page_id, 0),
            )
        )

    payload = "\n".join(e.model_dump_json() for e in entries)
    content_sha = hashlib.sha256(payload.encode("utf-8")).hexdigest()
    manifest = HandwritingSeedQueueManifest(
        created_at=_now(),
        page_count=len(entries),
        content_sha256=content_sha,
        uncertain_source_page_count=len(
            {
                e.opaque_page_reference
                for e in entries
                if "uncertain_prototype_crop_page" in e.priority_reasons
            }
        ),
        coverage_worklist_page_count=len(
            {e.opaque_page_reference for e in entries if "coverage_worklist" in e.priority_reasons}
        ),
        police_form_page_count=len(
            {e.opaque_page_reference for e in entries if "police_form" in e.priority_reasons}
        ),
        entries=entries,
    )
    write_jsonl_atomic(manifest_path(private_root, "handwriting-seed-queue.jsonl"), [manifest])
    return {
        "command": "handwriting-seeds-queue",
        "queue_version": HANDWRITING_SEED_QUEUE_VERSION,
        "page_count": manifest.page_count,
        "content_sha256": manifest.content_sha256,
        "uncertain_source_page_count": manifest.uncertain_source_page_count,
        "coverage_worklist_page_count": manifest.coverage_worklist_page_count,
        "police_form_page_count": manifest.police_form_page_count,
        "target_regions": HANDWRITING_SEED_TARGET_REGIONS,
    }


def load_seed_queue(private_root: Path) -> HandwritingSeedQueueManifest | None:
    queues = read_jsonl(
        manifest_path(private_root, "handwriting-seed-queue.jsonl"),
        HandwritingSeedQueueManifest,
    )
    return queues[-1] if queues else None


def seed_page_state(private_root: Path) -> dict[str, str]:
    """Latest terminal page action closes the page for queue advance."""

    events = read_jsonl(
        manifest_path(private_root, "handwriting-seed-events.jsonl"), HandwritingSeedEvent
    )
    state: dict[str, str] = {}
    for event in events:
        if event.action in {"no_usable_handwriting", "defer", "complete_page"}:
            state[event.opaque_page_reference] = event.action
        elif event.action in {"confirm_region", "select_existing_crop"}:
            # Creating a seed does not close the page; human may add more regions.
            state.pop(event.opaque_page_reference, None)
    return state


def seed_progress(private_root: Path) -> dict[str, Any]:
    queue = load_seed_queue(private_root)
    records = read_jsonl(
        manifest_path(private_root, "handwriting-seed-records.jsonl"), HandwritingSeedRecord
    )
    page_state = seed_page_state(private_root)
    closed = {
        p
        for p, action in page_state.items()
        if action in {"no_usable_handwriting", "defer", "complete_page"}
    }
    total = queue.page_count if queue else 0
    remaining = 0
    if queue:
        remaining = sum(1 for e in queue.entries if e.opaque_page_reference not in closed)
    active = sum(1 for r in records if r.status == "active")
    return {
        "pages_offered": total,
        "pages_remaining": remaining,
        "pages_closed": len(closed),
        "seed_records_total": len(records),
        "seed_records_active": active,
        "target_regions": HANDWRITING_SEED_TARGET_REGIONS,
    }


def page_guide_crops(private_root: Path, opaque_page_reference: str) -> list[dict[str, Any]]:
    """Optional visual guides: crop geometry only (no text / labels / paths)."""

    crops = [
        c
        for c in read_jsonl(manifest_path(private_root, "crop-manifest.jsonl"), CropRecord)
        if c.page_id == opaque_page_reference
    ]
    resolved = {
        r.crop_id: r
        for r in read_jsonl(
            manifest_path(private_root, "resolved-labels.jsonl"), ResolvedLabelRecord
        )
    }
    guides: list[dict[str, Any]] = []
    for crop in crops:
        label = resolved.get(crop.crop_id)
        guides.append(
            {
                "crop_id": crop.crop_id,
                "bbox": {
                    "x": crop.source_bbox.x,
                    "y": crop.source_bbox.y,
                    "width": crop.source_bbox.width,
                    "height": crop.source_bbox.height,
                },
                # Opaque flag only — does not reinterpret; UI may highlight prior uncertain.
                "was_uncertain": bool(label is not None and label.label == "uncertain"),
            }
        )
    return guides


def confirm_drawn_region(
    *,
    private_root: Path,
    opaque_page_reference: str,
    opaque_document_reference: str,
    source_group_id: str,
    reviewer_id: str,
    bbox: dict[str, float],
    parent_crop_id: str | None = None,
    categories: list[str] | None = None,
) -> dict[str, Any]:
    """Human-confirmed drawn region → crop + seed event + seed record."""

    if not reviewer_id_ok(reviewer_id):
        raise ValueError("reviewer_id must start with handwriting_reviewer_")
    geometry = NormalisedBoundingBox(
        x=float(bbox["x"]),
        y=float(bbox["y"]),
        width=float(bbox["width"]),
        height=float(bbox["height"]),
    )
    warnings = geometry_warnings(geometry)
    page_hash = page_render_sha256(private_root, opaque_page_reference)
    if page_hash is None:
        raise ValueError("missing page render")
    page_path = pages_dir(private_root) / f"{opaque_page_reference}.png"
    crops_path = manifest_path(private_root, "crop-manifest.jsonl")
    existing = index_by(read_jsonl(crops_path, CropRecord), lambda c: c.crop_id)
    sources = {
        s.page_id: s
        for s in read_jsonl(manifest_path(private_root, "source-manifest.jsonl"), SourceRecord)
    }
    src = sources.get(opaque_page_reference)
    page_index = src.page_index if src else 0
    with Image.open(page_path) as img:
        page = img.convert("RGB")
        crop = export_crop_from_page(
            private_root=private_root,
            page_image=page,
            source_bbox=geometry,
            source_polygon=None,
            candidate_source="manual_region",
            source_group_id=source_group_id,
            document_id=opaque_document_reference,
            page_id=opaque_page_reference,
            page_index=page_index,
            existing_by_key=existing,
        )
    if crop is None:
        # Identical geometry already exported — reuse existing crop record.
        for existing_crop in existing.values():
            if (
                existing_crop.page_id == opaque_page_reference
                and existing_crop.candidate_source == "manual_region"
                and abs(existing_crop.source_bbox.x - geometry.x) < 1e-9
                and abs(existing_crop.source_bbox.y - geometry.y) < 1e-9
                and abs(existing_crop.source_bbox.width - geometry.width) < 1e-9
                and abs(existing_crop.source_bbox.height - geometry.height) < 1e-9
            ):
                crop = existing_crop
                break
        if crop is None:
            raise ValueError("failed to export or locate crop for region")
    else:
        append_jsonl(crops_path, [crop])

    seed_region_id = new_handwriting_seed_region_id()
    cats = _parse_categories(categories)
    source_reference = (
        f"parent_crop:{parent_crop_id}" if parent_crop_id else f"manual_draw:{seed_region_id}"
    )
    record = HandwritingSeedRecord(
        seed_region_id=seed_region_id,
        opaque_document_id=opaque_document_reference,
        opaque_page_reference=opaque_page_reference,
        source_group_id=source_group_id,
        reviewer_id=reviewer_id,
        geometry_normalized=geometry,
        page_render_sha256=page_hash,
        crop_sha256=crop.sha256,
        perceptual_hash=crop.perceptual_hash,
        source_type=HANDWRITING_SEED_SOURCE_TYPE,
        source_reference=source_reference,
        crop_id=crop.crop_id,
        parent_crop_id=parent_crop_id,
        categories=cats,
        status="active",
        created_at=_now(),
    )
    event = HandwritingSeedEvent(
        seed_event_id=new_handwriting_seed_event_id(),
        opaque_page_reference=opaque_page_reference,
        opaque_document_reference=opaque_document_reference,
        source_group_id=source_group_id,
        reviewer_id=reviewer_id,
        action="confirm_region",
        page_render_sha256=page_hash,
        geometry_normalized=geometry,
        parent_crop_id=parent_crop_id,
        seed_region_id=seed_region_id,
        crop_id=crop.crop_id,
        categories=cats,
        geometry_warnings=warnings,
        created_at=_now(),
    )
    append_jsonl(manifest_path(private_root, "handwriting-seed-events.jsonl"), [event])
    append_jsonl(manifest_path(private_root, "handwriting-seed-records.jsonl"), [record])
    return {
        "ok": True,
        "seed_region_id": seed_region_id,
        "crop_id": crop.crop_id,
        "geometry_warnings": warnings,
        "action": "confirm_region",
    }


def select_existing_crop(
    *,
    private_root: Path,
    opaque_page_reference: str,
    opaque_document_reference: str,
    source_group_id: str,
    reviewer_id: str,
    parent_crop_id: str,
    categories: list[str] | None = None,
) -> dict[str, Any]:
    """Human selects an existing crop that cleanly contains handwriting."""

    if not reviewer_id_ok(reviewer_id):
        raise ValueError("reviewer_id must start with handwriting_reviewer_")
    crops = index_by(
        read_jsonl(manifest_path(private_root, "crop-manifest.jsonl"), CropRecord),
        lambda c: c.crop_id,
    )
    crop = crops.get(parent_crop_id)
    if crop is None:
        raise ValueError("unknown parent_crop_id")
    if crop.page_id != opaque_page_reference:
        raise ValueError("parent_crop_id is not on this page")
    page_hash = page_render_sha256(private_root, opaque_page_reference)
    if page_hash is None:
        raise ValueError("missing page render")
    # Do not mutate prior review events; seed record is the handwritten confirmation.
    seed_region_id = new_handwriting_seed_region_id()
    cats = _parse_categories(categories)
    geometry = crop.source_bbox
    warnings = geometry_warnings(geometry)
    record = HandwritingSeedRecord(
        seed_region_id=seed_region_id,
        opaque_document_id=opaque_document_reference,
        opaque_page_reference=opaque_page_reference,
        source_group_id=source_group_id,
        reviewer_id=reviewer_id,
        geometry_normalized=geometry,
        page_render_sha256=page_hash,
        crop_sha256=crop.sha256,
        perceptual_hash=crop.perceptual_hash,
        source_type=HANDWRITING_SEED_SOURCE_TYPE,
        source_reference=f"selected_crop:{parent_crop_id}",
        crop_id=crop.crop_id,
        parent_crop_id=parent_crop_id,
        categories=cats,
        status="active",
        created_at=_now(),
    )
    event = HandwritingSeedEvent(
        seed_event_id=new_handwriting_seed_event_id(),
        opaque_page_reference=opaque_page_reference,
        opaque_document_reference=opaque_document_reference,
        source_group_id=source_group_id,
        reviewer_id=reviewer_id,
        action="select_existing_crop",
        page_render_sha256=page_hash,
        geometry_normalized=geometry,
        parent_crop_id=parent_crop_id,
        seed_region_id=seed_region_id,
        crop_id=crop.crop_id,
        categories=cats,
        geometry_warnings=warnings,
        created_at=_now(),
    )
    append_jsonl(manifest_path(private_root, "handwriting-seed-events.jsonl"), [event])
    append_jsonl(manifest_path(private_root, "handwriting-seed-records.jsonl"), [record])
    return {
        "ok": True,
        "seed_region_id": seed_region_id,
        "crop_id": crop.crop_id,
        "geometry_warnings": warnings,
        "action": "select_existing_crop",
    }


def close_page(
    *,
    private_root: Path,
    opaque_page_reference: str,
    opaque_document_reference: str,
    source_group_id: str,
    reviewer_id: str,
    action: str,
) -> dict[str, Any]:
    if action not in {"no_usable_handwriting", "defer", "complete_page"}:
        raise ValueError("action must be no_usable_handwriting, defer, or complete_page")
    if not reviewer_id_ok(reviewer_id):
        raise ValueError("reviewer_id must start with handwriting_reviewer_")
    page_hash = page_render_sha256(private_root, opaque_page_reference)
    if page_hash is None:
        raise ValueError("missing page render")
    close_action = cast(SeedCloseAction, action)
    event = HandwritingSeedEvent(
        seed_event_id=new_handwriting_seed_event_id(),
        opaque_page_reference=opaque_page_reference,
        opaque_document_reference=opaque_document_reference,
        source_group_id=source_group_id,
        reviewer_id=reviewer_id,
        action=close_action,
        page_render_sha256=page_hash,
        created_at=_now(),
    )
    append_jsonl(manifest_path(private_root, "handwriting-seed-events.jsonl"), [event])
    return {"ok": True, "action": action}


def verify_handwriting_seeds(private_root: Path) -> list[str]:
    """Return integrity problems (empty = ok). Does not mutate prior review events."""

    problems: list[str] = []
    records = read_jsonl(
        manifest_path(private_root, "handwriting-seed-records.jsonl"), HandwritingSeedRecord
    )
    events = read_jsonl(
        manifest_path(private_root, "handwriting-seed-events.jsonl"), HandwritingSeedEvent
    )
    crops = index_by(
        read_jsonl(manifest_path(private_root, "crop-manifest.jsonl"), CropRecord),
        lambda c: c.crop_id,
    )
    for event in events:
        if event.action in {"confirm_region", "select_existing_crop"}:
            if event.crop_id and event.crop_id not in crops:
                problems.append(f"event {event.seed_event_id}: missing crop")
            if event.page_render_sha256 != page_render_sha256(
                private_root, event.opaque_page_reference
            ):
                problems.append(f"event {event.seed_event_id}: page hash mismatch")
    for record in records:
        crop = crops.get(record.crop_id)
        if crop is None:
            problems.append(f"seed {record.seed_region_id}: missing crop")
            continue
        path = private_root / crop.crop_relpath
        if not path.is_file():
            problems.append(f"seed {record.seed_region_id}: missing crop file")
            continue
        if sha256_file(path) != record.crop_sha256:
            problems.append(f"seed {record.seed_region_id}: crop hash mismatch")
        if crop.sha256 != record.crop_sha256:
            problems.append(f"seed {record.seed_region_id}: crop manifest hash mismatch")
        geom_mismatch = (
            abs(crop.source_bbox.x - record.geometry_normalized.x) > 1e-9
            or abs(crop.source_bbox.y - record.geometry_normalized.y) > 1e-9
            or abs(crop.source_bbox.width - record.geometry_normalized.width) > 1e-9
            or abs(crop.source_bbox.height - record.geometry_normalized.height) > 1e-9
        )
        # Selected existing crops use source geometry; drawn seeds should match.
        drawn = record.parent_crop_id is None or record.source_reference.startswith("manual_draw")
        if geom_mismatch and drawn:
            problems.append(f"seed {record.seed_region_id}: geometry mismatch")
    return problems


def resolve_exact_duplicates(private_root: Path) -> dict[str, Any]:
    """Mark byte-identical seed crops as exact_duplicate; keep one active canonical."""

    records = read_jsonl(
        manifest_path(private_root, "handwriting-seed-records.jsonl"), HandwritingSeedRecord
    )
    by_sha: dict[str, list[HandwritingSeedRecord]] = {}
    for record in records:
        by_sha.setdefault(record.crop_sha256, []).append(record)
    updated: list[HandwritingSeedRecord] = []
    exact_dup_count = 0
    for _sha, family in by_sha.items():
        family_sorted = sorted(family, key=lambda r: (r.created_at.isoformat(), r.seed_region_id))
        canonical = family_sorted[0]
        for idx, record in enumerate(family_sorted):
            if idx == 0:
                updated.append(
                    record.model_copy(
                        update={"status": "active", "duplicate_of_seed_region_id": None}
                    )
                )
            else:
                exact_dup_count += 1
                updated.append(
                    record.model_copy(
                        update={
                            "status": "exact_duplicate",
                            "duplicate_of_seed_region_id": canonical.seed_region_id,
                        }
                    )
                )
    write_jsonl_atomic(manifest_path(private_root, "handwriting-seed-records.jsonl"), updated)
    return {
        "seed_records": len(updated),
        "canonical_active": sum(1 for r in updated if r.status == "active"),
        "exact_duplicates": exact_dup_count,
    }


def perceptual_duplicate_warnings(private_root: Path) -> list[str]:
    records = [
        r
        for r in read_jsonl(
            manifest_path(private_root, "handwriting-seed-records.jsonl"), HandwritingSeedRecord
        )
        if r.status == "active"
    ]
    warnings: list[str] = []
    for i, a in enumerate(records):
        for b in records[i + 1 :]:
            if a.crop_sha256 == b.crop_sha256:
                continue
            dist = hamming_hex(a.perceptual_hash, b.perceptual_hash)
            if dist <= PERCEPTUAL_HAMMING_WARN_THRESHOLD:
                warnings.append(f"perceptual near-duplicate warning: seeds distance={dist}")
    return warnings


def build_handwriting_seed_aggregate(private_root: Path) -> dict[str, Any]:
    queue = load_seed_queue(private_root)
    events = read_jsonl(
        manifest_path(private_root, "handwriting-seed-events.jsonl"), HandwritingSeedEvent
    )
    records = read_jsonl(
        manifest_path(private_root, "handwriting-seed-records.jsonl"), HandwritingSeedRecord
    )
    sources = {
        s.page_id: s
        for s in read_jsonl(manifest_path(private_root, "source-manifest.jsonl"), SourceRecord)
    }
    documents = {
        d.document_id: d
        for d in read_jsonl(manifest_path(private_root, "document-manifest.jsonl"), DocumentRecord)
    }

    inspected_pages: set[str] = set()
    for event in events:
        inspected_pages.add(event.opaque_page_reference)
    pages_with_seeds = {r.opaque_page_reference for r in records}
    no_usable = sum(1 for e in events if e.action == "no_usable_handwriting")
    deferred = sum(1 for e in events if e.action == "defer")
    pages_completed = sum(1 for e in events if e.action == "complete_page")
    active = [r for r in records if r.status == "active"]
    exact_dups = sum(1 for r in records if r.status == "exact_duplicate")
    categories: Counter[str] = Counter()
    for record in active:
        for cat in record.categories:
            categories[cat] += 1
    groups = {r.source_group_id for r in active}
    families: Counter[str] = Counter()
    for record in active:
        families[
            _family_for_page(
                page_id=record.opaque_page_reference, sources=sources, documents=documents
            )
        ] += 1
    # Suppress tiny family buckets in committed reports.
    family_safe = {k: v for k, v in families.items() if v >= 3}
    suppressed = sum(v for k, v in families.items() if v < 3)

    uncertain_pages = 0
    coverage_pages = 0
    if queue:
        for entry in queue.entries:
            if "uncertain_prototype_crop_page" in entry.priority_reasons:
                uncertain_pages += 1
            if "coverage_worklist" in entry.priority_reasons:
                coverage_pages += 1

    perceptual = perceptual_duplicate_warnings(private_root)
    canonical = len(active)
    sufficient = canonical >= 40 and len(groups) >= 2
    readiness = (
        "PROJECT HANDWRITING SEED READY"
        if sufficient
        else "PROJECT HANDWRITING SEED REQUIRES EXTERNAL SUPPLEMENT"
    )
    return {
        "report_version": HANDWRITING_SEED_REPORT_VERSION,
        "seed_schema_version": HANDWRITING_SEED_SCHEMA_VERSION,
        "pages_offered": queue.page_count if queue else 0,
        "pages_inspected": len(inspected_pages),
        "pages_with_usable_handwriting": len(pages_with_seeds),
        "regions_created_or_selected": len(records),
        "canonical_after_exact_dedupe": canonical,
        "source_groups_represented": len(groups),
        "broad_family_counts": dict(sorted(family_safe.items())),
        "broad_family_suppressed_count": suppressed,
        "category_counts": dict(sorted(categories.items())),
        "excluded_no_usable": no_usable,
        "deferred": deferred,
        "pages_completed": pages_completed,
        "exact_duplicates": exact_dups,
        "perceptual_warning_count": len(perceptual),
        "uncertain_source_pages_in_queue": uncertain_pages,
        "coverage_worklist_pages_in_queue": coverage_pages,
        "target_regions": HANDWRITING_SEED_TARGET_REGIONS,
        "readiness": readiness,
        "external_supplement_recommended": not sufficient
        or canonical < HANDWRITING_SEED_TARGET_REGIONS,
        "sufficient_for_prototype_attempt": sufficient,
    }


def render_handwriting_seed_readiness_markdown(report: dict[str, Any]) -> str:
    families = report.get("broad_family_counts") or {}
    cats = report.get("category_counts") or {}
    family_lines = "\n".join(f"- `{k}`: **{v}**" for k, v in families.items()) or "- _(none)_"
    cat_lines = "\n".join(f"- `{k}`: **{v}**" for k, v in cats.items()) or "- _(none recorded)_"
    return f"""# Phase 5 handwriting seed readiness

**Status:** {report.get("readiness")}

Aggregate / opaque only. No private IDs, page references, filenames, paths,
reviewer IDs, hashes, or visible text.

## Candidate pages

1. Candidate pages offered: **{report.get("pages_offered")}**
2. Candidate pages inspected: **{report.get("pages_inspected")}**
3. Pages containing usable handwriting: **{report.get("pages_with_usable_handwriting")}**
4. Human-confirmed handwritten regions: **{report.get("regions_created_or_selected")}**
5. Canonical regions after exact deduplication: **{report.get("canonical_after_exact_dedupe")}**
6. Source groups represented: **{report.get("source_groups_represented")}**
7. Broad source families represented (privacy-safe):

{family_lines}

- Suppressed small family buckets (seed count):
  **{report.get("broad_family_suppressed_count")}**

8. Handwritten region categories (structured tags only):

{cat_lines}

9. Excluded (no usable handwriting): **{report.get("excluded_no_usable")}**
10. Deferred: **{report.get("deferred")}**
11. Pages marked complete after seed collection: **{report.get("pages_completed")}**
12. Exact duplicate count: **{report.get("exact_duplicates")}**
13. Perceptual duplicate warnings: **{report.get("perceptual_warning_count")}**

### Queue composition (aggregate)

- Uncertain-source pages included: **{report.get("uncertain_source_pages_in_queue")}**
- Coverage-worklist pages included: **{report.get("coverage_worklist_pages_in_queue")}**
- Target region count: **{report.get("target_regions")}**

## Known limitations

- Private crops originate from combined Paddle detection/recognition evidence.
- Empty-text detections were dropped from the original corpus.
- Handwriting Paddle failed to detect may still be underrepresented until seeds
  are added.
- Signatures and handwritten form values were historically underrepresented.
- The 54 prototype `uncertain` labels were not automatically reinterpreted.
- Seed collection is human-only; no dual review, adjudication, or held-out
  freeze in Task A2.

## Readiness

- Project seed sufficient to attempt prototype model development:
  **{"yes" if report.get("sufficient_for_prototype_attempt") else "no"}**
- External handwriting supplementation recommended:
  **{"yes" if report.get("external_supplement_recommended") else "no"}**

## Policy

- Report version: `{report.get("report_version")}`
- Seed schema: `{report.get("seed_schema_version")}`
- Source type: `human_confirmed_handwriting_seed`
- No OCR, classifier, vision provider, or transcription in Task A2.
- Existing prototype review events were not mutated.

See `docs/operations/phase-5-labelling.md` and ADR 0053 / Task A2.
"""
