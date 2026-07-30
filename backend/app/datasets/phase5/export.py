"""Crop export from Phase 4 artefacts and manual regions."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from PIL import Image

from backend.app.contracts.geometry import NormalisedBoundingBox, NormalisedPolygon
from backend.app.datasets.phase5.constants import CANDIDATE_SOURCES
from backend.app.datasets.phase5.hashes import png_bytes_and_hashes, sha256_file
from backend.app.datasets.phase5.ids import (
    new_crop_id,
    new_document_id,
    new_page_id,
    new_source_group_id,
)
from backend.app.datasets.phase5.jsonl_io import append_jsonl, index_by, read_jsonl
from backend.app.datasets.phase5.padding import apply_crop_padding, bbox_from_polygon_points
from backend.app.datasets.phase5.paths import crops_dir, ensure_layout, manifest_path
from backend.app.datasets.phase5.schemas import (
    CandidateSource,
    CropRecord,
    SourceRecord,
)

# Mapping from Phase 4 artefact kinds → candidate_source (geometry only; never labels).
PHASE4_SOURCE_MAP: dict[str, CandidateSource] = {
    "line": "full_page_ocr",
    "word": "full_page_ocr",
    "block": "visual_detection",
    "visual_block": "visual_detection",
    "repair": "targeted_repair",
    "repair_region": "targeted_repair",
    "heuristic": "heuristic_region",
    "noise": "noise_region",
    "manual": "manual_region",
    "synthetic_negative": "synthetic_negative",
}


def _now() -> datetime:
    return datetime.now(UTC)


def _crop_pixels(page: Image.Image, bbox: NormalisedBoundingBox) -> Image.Image:
    w, h = page.size
    x0 = int(max(0, min(w - 1, round(bbox.x * w))))
    y0 = int(max(0, min(h - 1, round(bbox.y * h))))
    x1 = int(max(x0 + 1, min(w, round((bbox.x + bbox.width) * w))))
    y1 = int(max(y0 + 1, min(h, round((bbox.y + bbox.height) * h))))
    return page.crop((x0, y0, x1, y1))


def _bbox_from_obj(obj: dict[str, Any]) -> NormalisedBoundingBox:
    if "bbox" in obj and isinstance(obj["bbox"], dict):
        b = obj["bbox"]
        return NormalisedBoundingBox(
            x=float(b["x"]),
            y=float(b["y"]),
            width=float(b["width"]),
            height=float(b["height"]),
        )
    if "normalised_bbox" in obj and isinstance(obj["normalised_bbox"], dict):
        b = obj["normalised_bbox"]
        return NormalisedBoundingBox(
            x=float(b["x"]),
            y=float(b["y"]),
            width=float(b["width"]),
            height=float(b["height"]),
        )
    if "polygon" in obj and isinstance(obj["polygon"], dict):
        pts = obj["polygon"].get("points") or []
        pairs = [(float(p["x"]), float(p["y"])) for p in pts]
        return bbox_from_polygon_points(pairs)
    raise ValueError("Region missing bbox/polygon geometry")


def _polygon_from_obj(obj: dict[str, Any]) -> NormalisedPolygon | None:
    poly = obj.get("polygon")
    if not isinstance(poly, dict):
        return None
    pts = poly.get("points") or []
    if len(pts) < 3:
        return None
    return NormalisedPolygon.model_validate(poly)


def extract_phase4_regions(
    page_result: dict[str, Any],
) -> list[tuple[CandidateSource, dict[str, Any]]]:
    """Pull geometry-bearing regions from a VisualPageResult-like JSON object.

    OCR text/confidence are ignored and must never become labels.
    """

    out: list[tuple[CandidateSource, dict[str, Any]]] = []
    for key, source in (
        ("blocks", "visual_detection"),
        ("lines", "full_page_ocr"),
        ("words", "full_page_ocr"),
    ):
        for item in page_result.get(key) or []:
            if isinstance(item, dict):
                out.append((source, item))  # type: ignore[arg-type]
    for item in page_result.get("repair_regions") or []:
        if isinstance(item, dict):
            out.append(("targeted_repair", item))
    return out


def export_crop_from_page(
    *,
    private_root: Path,
    page_image: Image.Image,
    source_bbox: NormalisedBoundingBox,
    source_polygon: NormalisedPolygon | None,
    candidate_source: CandidateSource,
    source_group_id: str,
    document_id: str,
    page_id: str,
    page_index: int,
    existing_by_key: dict[str, CropRecord],
) -> CropRecord | None:
    """Export one crop; skip if an identical resume key already exists."""

    crop_bbox, applied = apply_crop_padding(source_bbox)
    resume_key = (
        f"{page_id}|{candidate_source}|"
        f"{source_bbox.x:.6f},{source_bbox.y:.6f},"
        f"{source_bbox.width:.6f},{source_bbox.height:.6f}"
    )
    # Resume uses geometry key stored indirectly via matching crop_bbox+page.
    for existing in existing_by_key.values():
        if (
            existing.page_id == page_id
            and existing.candidate_source == candidate_source
            and abs(existing.source_bbox.x - source_bbox.x) < 1e-9
            and abs(existing.source_bbox.y - source_bbox.y) < 1e-9
            and abs(existing.source_bbox.width - source_bbox.width) < 1e-9
            and abs(existing.source_bbox.height - source_bbox.height) < 1e-9
        ):
            crop_path = private_root / existing.crop_relpath
            if crop_path.is_file() and sha256_file(crop_path) == existing.sha256:
                return None

    cropped = _crop_pixels(page_image, crop_bbox)
    data, sha, phash = png_bytes_and_hashes(cropped)
    crop_id = new_crop_id()
    rel = f"crops/{crop_id}.png"
    out_path = private_root / rel
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_bytes(data)
    record = CropRecord(
        crop_id=crop_id,
        source_group_id=source_group_id,
        document_id=document_id,
        page_id=page_id,
        page_index=page_index,
        candidate_source=candidate_source,
        source_bbox=source_bbox,
        source_polygon=source_polygon,
        crop_bbox=crop_bbox,
        applied_padding=applied,
        crop_relpath=rel.replace("\\", "/"),
        sha256=sha,
        perceptual_hash=phash,
        width_px=cropped.size[0],
        height_px=cropped.size[1],
        created_at=_now(),
    )
    _ = resume_key
    return record


def export_from_phase4_json(
    *,
    private_root: Path,
    page_result_path: Path,
    page_image_path: Path,
    source_group_id: str | None = None,
    document_id: str | None = None,
    page_id: str | None = None,
    kinds: set[str] | None = None,
) -> list[CropRecord]:
    """Export crops from a Phase 4 VisualPageResult JSON + page PNG/JPEG."""

    ensure_layout(private_root)
    payload = json.loads(page_result_path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("Phase 4 page result must be a JSON object")
    page_index = int(payload.get("page_number", 1)) - 1
    if page_index < 0:
        page_index = 0
    sg = source_group_id or new_source_group_id()
    doc = document_id or new_document_id()
    pg = page_id or new_page_id()

    sources_path = manifest_path(private_root, "source-manifest.jsonl")
    crops_path = manifest_path(private_root, "crop-manifest.jsonl")
    existing_crops = index_by(read_jsonl(crops_path, CropRecord), lambda c: c.crop_id)

    source = SourceRecord(
        source_group_id=sg,
        document_id=doc,
        page_id=pg,
        page_index=page_index,
        page_width_px=None,
        page_height_px=None,
        page_relpath=None,
        created_at=_now(),
    )
    with Image.open(page_image_path) as img:
        page = img.convert("RGB")
        source = source.model_copy(
            update={"page_width_px": page.size[0], "page_height_px": page.size[1]}
        )
        append_jsonl(sources_path, [source])
        created: list[CropRecord] = []
        allow = kinds or {"blocks", "lines", "words", "repair_regions"}
        regions = extract_phase4_regions(payload)
        for candidate_source, item in regions:
            # Filter by artefact family when kinds is set.
            if "blocks" not in allow and candidate_source == "visual_detection":
                continue
            # Export all full_page_ocr geometry when either lines or words allowed.
            if (
                candidate_source == "full_page_ocr"
                and "lines" not in allow
                and "words" not in allow
            ):
                continue
            if candidate_source == "targeted_repair" and "repair_regions" not in allow:
                continue
            try:
                bbox = _bbox_from_obj(item)
                poly = _polygon_from_obj(item)
            except (ValueError, KeyError, TypeError):
                continue
            rec = export_crop_from_page(
                private_root=private_root,
                page_image=page,
                source_bbox=bbox,
                source_polygon=poly,
                candidate_source=candidate_source,
                source_group_id=sg,
                document_id=doc,
                page_id=pg,
                page_index=page_index,
                existing_by_key=existing_crops,
            )
            if rec is not None:
                created.append(rec)
                existing_crops[rec.crop_id] = rec
        if created:
            append_jsonl(crops_path, created)
        return created


def import_manual_regions(
    *,
    private_root: Path,
    regions_jsonl: Path,
    page_image_path: Path,
    source_group_id: str | None = None,
    document_id: str | None = None,
    page_id: str | None = None,
    page_index: int = 0,
) -> list[CropRecord]:
    """Import validated manual regions (JSONL) and write crops.

    Each line: ``{"bbox": {...}, "polygon": optional, "candidate_source": optional}``.
    Default candidate_source is ``manual_region``.
    """

    ensure_layout(private_root)
    sg = source_group_id or new_source_group_id()
    doc = document_id or new_document_id()
    pg = page_id or new_page_id()
    crops_path = manifest_path(private_root, "crop-manifest.jsonl")
    sources_path = manifest_path(private_root, "source-manifest.jsonl")
    existing = index_by(read_jsonl(crops_path, CropRecord), lambda c: c.crop_id)
    created: list[CropRecord] = []
    with Image.open(page_image_path) as img:
        page = img.convert("RGB")
        append_jsonl(
            sources_path,
            [
                SourceRecord(
                    source_group_id=sg,
                    document_id=doc,
                    page_id=pg,
                    page_index=page_index,
                    page_width_px=page.size[0],
                    page_height_px=page.size[1],
                    page_relpath=None,
                    created_at=_now(),
                )
            ],
        )
        for line_no, line in enumerate(
            regions_jsonl.read_text(encoding="utf-8").splitlines(), start=1
        ):
            text = line.strip()
            if not text:
                continue
            try:
                obj = json.loads(text)
            except json.JSONDecodeError as exc:
                raise ValueError(f"{regions_jsonl}:{line_no}: invalid JSON") from exc
            if not isinstance(obj, dict):
                raise ValueError(f"{regions_jsonl}:{line_no}: expected object")
            # Reject text fields that would leak OCR into labels/manifests.
            for banned in ("text", "ocr_text", "transcript", "label", "filename"):
                if banned in obj:
                    raise ValueError(
                        f"{regions_jsonl}:{line_no}: forbidden field '{banned}' "
                        "(geometry-only; human labels come from the labeler)"
                    )
            src = obj.get("candidate_source", "manual_region")
            allowed_sources = CANDIDATE_SOURCES | set(PHASE4_SOURCE_MAP)
            if src not in allowed_sources:
                raise ValueError(f"{regions_jsonl}:{line_no}: bad candidate_source")
            mapped = PHASE4_SOURCE_MAP.get(src, src)
            if mapped not in CANDIDATE_SOURCES:
                raise ValueError(f"{regions_jsonl}:{line_no}: bad candidate_source")
            candidate = mapped  # narrowed by membership check above
            bbox = _bbox_from_obj(obj)
            poly = _polygon_from_obj(obj)
            rec = export_crop_from_page(
                private_root=private_root,
                page_image=page,
                source_bbox=bbox,
                source_polygon=poly,
                candidate_source=candidate,
                source_group_id=sg,
                document_id=doc,
                page_id=pg,
                page_index=page_index,
                existing_by_key=existing,
            )
            if rec is not None:
                created.append(rec)
                existing[rec.crop_id] = rec
    if created:
        append_jsonl(crops_path, created)
    return created


def verify_crops(private_root: Path) -> list[str]:
    """Return consistency problems (empty = ok)."""

    problems: list[str] = []
    crops_path = manifest_path(private_root, "crop-manifest.jsonl")
    for crop in read_jsonl(crops_path, CropRecord):
        path = private_root / crop.crop_relpath
        if not path.is_file():
            problems.append(f"missing crop file for {crop.crop_id}")
            continue
        digest = sha256_file(path)
        if digest != crop.sha256:
            problems.append(f"sha256 mismatch for {crop.crop_id}")
        try:
            with Image.open(path) as img:
                if img.size[0] != crop.width_px or img.size[1] != crop.height_px:
                    problems.append(f"size mismatch for {crop.crop_id}")
        except OSError as exc:
            problems.append(f"unreadable crop {crop.crop_id}: {exc}")
        # Geometry bounds
        b = crop.crop_bbox
        if b.x < 0 or b.y < 0 or b.x + b.width > 1.0 + 1e-6 or b.y + b.height > 1.0 + 1e-6:
            problems.append(f"crop_bbox out of page for {crop.crop_id}")
    return problems


def init_private_dataset(private_root: Path) -> Path:
    ensure_layout(private_root)
    crops_dir(private_root).mkdir(parents=True, exist_ok=True)
    return private_root
