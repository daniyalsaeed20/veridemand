"""Annotation persistence helpers for the private review app."""

from __future__ import annotations

import json
import re
import shutil
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SCHEMA_LABEL = "EVALUATION SCHEMA — NOT YET PRODUCTION CONTRACT"

PAGE_ID_RE = re.compile(r"^[A-Za-z0-9_\-]+$")

ANNOTATION_STATUSES = frozenset(
    {
        "machine_prefill",
        "in_review",
        "human_reviewed",
        "needs_second_review",
        "unreadable",
    }
)

QUESTION_KEYS = [
    "text_matches_visible_page",
    "words_missing",
    "extra_words_present",
    "reading_order_correct",
    "boxes_enclose_correct_words",
    "native_text_layer_trustworthy",
    "fresh_ocr_required",
    "page_unreadable",
    "critical_values_exact",
]

ANSWER_VALUES = frozenset({"Yes", "No", "Partly", "Not applicable", "Unsure", ""})


def empty_questions() -> dict[str, str]:
    return {k: "" for k in QUESTION_KEYS}


def new_annotation(
    *,
    page_id: str,
    case_alias: str,
    doc_alias: str,
    page_number: int,
    machine_transcript: str = "",
    critical_fields: list[dict] | None = None,
    challenges: list[str] | None = None,
) -> dict[str, Any]:
    return {
        "schema_label": SCHEMA_LABEL,
        "page_id": page_id,
        "case_alias": case_alias,
        "doc_alias": doc_alias,
        "page_number": page_number,
        "annotation_status": "machine_prefill",
        "ground_truth_ready": False,
        "prefill_label": "UNVERIFIED MACHINE OUTPUT",
        "machine_transcript": machine_transcript,
        "expected_transcript": "",
        "machine_reading_order": [],
        "expected_reading_order": [],
        "reading_order_confirmed": False,
        "order_issue_flags": [],
        "expected_boxes": [],
        "critical_fields": critical_fields or [],
        "questions": empty_questions(),
        "notes": "",
        "reviewer": "",
        "review_date": "",
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "revision": 0,
        "etag": str(uuid.uuid4()),
        "machine_prefill_ref": "machine_prefill.json",
        "challenges": challenges or [],
        "geometry_review_complete": False,
        "text_review_complete": False,
        "order_review_complete": False,
    }


def validate_page_id(page_id: str) -> None:
    if not page_id or not PAGE_ID_RE.match(page_id):
        raise ValueError("invalid page_id")


def safe_resolve(root: Path, *parts: str) -> Path:
    """Resolve a path under root; reject traversal."""
    root = root.resolve()
    for part in parts:
        if not part or part in {".", ".."} or "/" in part or "\\" in part or ":" in part:
            raise ValueError("path traversal rejected")
    candidate = root.joinpath(*parts).resolve()
    try:
        candidate.relative_to(root)
    except ValueError as exc:
        raise ValueError("path outside annotation root") from exc
    return candidate


def validate_polygon(poly: Any) -> list[str]:
    errors: list[str] = []
    if not isinstance(poly, list) or len(poly) < 3:
        return ["polygon needs >= 3 points"]
    for i, pt in enumerate(poly):
        if not isinstance(pt, (list, tuple)) or len(pt) != 2:
            errors.append(f"point {i} invalid")
            continue
        x, y = float(pt[0]), float(pt[1])
        if not (0.0 - 1e-6 <= x <= 1.0 + 1e-6 and 0.0 - 1e-6 <= y <= 1.0 + 1e-6):
            errors.append(f"point {i} out of bounds")
    return errors


def validate_annotation(data: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if data.get("schema_label") != SCHEMA_LABEL:
        errors.append("schema_label invalid")
    try:
        validate_page_id(str(data.get("page_id") or ""))
    except ValueError:
        errors.append("page_id invalid")
    if data.get("annotation_status") not in ANNOTATION_STATUSES:
        errors.append("annotation_status invalid")
    if "machine_transcript" not in data:
        errors.append("machine_transcript missing")
    if "expected_transcript" not in data:
        errors.append("expected_transcript missing")
    if not isinstance(data.get("revision"), int) or data["revision"] < 0:
        errors.append("revision invalid")
    qs = data.get("questions")
    if not isinstance(qs, dict):
        errors.append("questions missing")
    else:
        for k in QUESTION_KEYS:
            if k not in qs:
                errors.append(f"question {k} missing")
            elif qs[k] not in ANSWER_VALUES:
                errors.append(f"question {k} has invalid answer")
    for box in data.get("expected_boxes") or []:
        if not isinstance(box, dict):
            errors.append("expected_box not object")
            continue
        gran = box.get("granularity")
        if gran not in {"region", "line", "word", "symbol"}:
            errors.append("box granularity invalid")
        errors.extend(validate_polygon(box.get("polygon")))
    return errors


def approval_blockers(data: dict[str, Any]) -> list[str]:
    """Return reasons a page cannot be marked human_reviewed."""
    blockers: list[str] = []
    status = data.get("annotation_status")
    unreadable = data.get("questions", {}).get("page_unreadable") == "Yes" or status == "unreadable"

    if not str(data.get("reviewer") or "").strip():
        blockers.append("reviewer_initials_required")
    if not str(data.get("review_date") or "").strip():
        blockers.append("review_date_required")

    qs = data.get("questions") or {}
    for k in QUESTION_KEYS:
        if not qs.get(k):
            blockers.append(f"question_unanswered:{k}")

    if not unreadable:
        if not str(data.get("expected_transcript") or "").strip():
            blockers.append("expected_transcript_required")
        if not data.get("reading_order_confirmed") and not data.get("order_review_complete"):
            blockers.append("reading_order_not_confirmed")
        if not data.get("geometry_review_complete"):
            # Representative geometry: at least confirm flag or one box for critical pages
            crit = data.get("critical_fields") or []
            needs_geom = any(c.get("requires_geometry_review") for c in crit)
            if needs_geom:
                boxes = data.get("expected_boxes") or []
                if not boxes:
                    blockers.append("critical_geometry_required")
            elif not data.get("geometry_review_complete"):
                blockers.append("geometry_review_incomplete")

    for field in data.get("critical_fields") or []:
        resolved = field.get("status") in {"exact", "incorrect", "unreadable"} or field.get(
            "match_status"
        ) in {"exact", "incorrect", "unreadable"}
        if not resolved:
            blockers.append(f"critical_unresolved:{field.get('field_id')}")

    return blockers


def can_mark_human_reviewed(data: dict[str, Any]) -> tuple[bool, list[str]]:
    # Special path: explicitly unreadable
    if data.get("questions", {}).get("page_unreadable") == "Yes":
        blockers = []
        if not str(data.get("reviewer") or "").strip():
            blockers.append("reviewer_initials_required")
        if not str(data.get("review_date") or "").strip():
            blockers.append("review_date_required")
        for k in QUESTION_KEYS:
            if not (data.get("questions") or {}).get(k):
                blockers.append(f"question_unanswered:{k}")
        return (len(blockers) == 0, blockers)
    blockers = approval_blockers(data)
    return (len(blockers) == 0, blockers)


class AnnotationStore:
    def __init__(self, review_root: Path) -> None:
        self.root = review_root.resolve()
        self.pages_dir = self.root / "pages"
        self.backups_dir = self.root / "backups"
        self.pages_dir.mkdir(parents=True, exist_ok=True)
        self.backups_dir.mkdir(parents=True, exist_ok=True)

    def page_dir(self, page_id: str) -> Path:
        validate_page_id(page_id)
        return safe_resolve(self.pages_dir, page_id)

    def annotation_path(self, page_id: str) -> Path:
        return self.page_dir(page_id) / "annotation.json"

    def load(self, page_id: str) -> dict[str, Any]:
        path = self.annotation_path(page_id)
        if not path.is_file():
            raise FileNotFoundError(page_id)
        return json.loads(path.read_text(encoding="utf-8"))

    def save(
        self,
        page_id: str,
        data: dict[str, Any],
        *,
        expected_etag: str | None = None,
        expected_revision: int | None = None,
    ) -> dict[str, Any]:
        validate_page_id(page_id)
        if data.get("page_id") != page_id:
            raise ValueError("page_id mismatch")
        errors = validate_annotation(data)
        if errors:
            raise ValueError("; ".join(errors))

        path = self.annotation_path(page_id)
        path.parent.mkdir(parents=True, exist_ok=True)

        if path.is_file():
            current = json.loads(path.read_text(encoding="utf-8"))
            if expected_etag is not None and current.get("etag") != expected_etag:
                raise ConflictError("stale etag")
            if expected_revision is not None and current.get("revision") != expected_revision:
                raise ConflictError("stale revision")
            # Preserve machine transcript unless explicitly same
            if "machine_transcript" in current:
                data["machine_transcript"] = current["machine_transcript"]
            if current.get("machine_prefill_ref"):
                data["machine_prefill_ref"] = current["machine_prefill_ref"]
            # Backup
            ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
            backup = self.backups_dir / f"{page_id}.{ts}.json"
            shutil.copy2(path, backup)

        data["updated_at"] = datetime.now(timezone.utc).isoformat()
        data["revision"] = int(data.get("revision") or 0) + 1
        data["etag"] = str(uuid.uuid4())
        if data.get("annotation_status") == "machine_prefill" and (
            data.get("expected_transcript") or data.get("reviewer")
        ):
            data["annotation_status"] = "in_review"

        tmp = path.with_suffix(".json.tmp")
        payload = json.dumps(data, indent=2) + "\n"
        with tmp.open("w", encoding="utf-8", newline="\n") as f:
            f.write(payload)
            f.flush()
            try:
                import os

                os.fsync(f.fileno())
            except OSError:
                pass
        tmp.replace(path)
        return data

    def list_page_ids(self) -> list[str]:
        if not self.pages_dir.is_dir():
            return []
        return sorted(
            p.name
            for p in self.pages_dir.iterdir()
            if p.is_dir() and (p / "annotation.json").is_file()
        )


class ConflictError(Exception):
    """Stale concurrent edit."""
