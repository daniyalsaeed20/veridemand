"""Schema validation for evaluation results and annotations."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

SCHEMA_LABEL = "EVALUATION SCHEMA — NOT YET PRODUCTION CONTRACT"

REPO_ROOT = Path(__file__).resolve().parents[2]
EVAL_SCHEMA_PATH = (
    REPO_ROOT / "docs" / "remediation" / "schemas" / "extraction-result-eval.schema.json"
)

INPUT_LAYERS = frozenset(
    {
        "native_pdf_text",
        "embedded_ocr",
        "fresh_ocr",
        "manual_correction",
        "model_assisted_review",
    }
)

ANNOTATION_STATUSES = frozenset(
    {
        "unreviewed",
        "machine_prefill",
        "human_approved",
        "disputed",
        "unreadable",
        "USER_CONFIRMED_ANCHOR",
    }
)

APPROVED_FOR_SOFT_METRICS = frozenset({"human_approved", "USER_CONFIRMED_ANCHOR"})


class SchemaValidationError(ValueError):
    """Raised when an evaluation payload fails validation."""


def load_eval_schema() -> dict[str, Any]:
    return json.loads(EVAL_SCHEMA_PATH.read_text(encoding="utf-8"))


def validate_engine_metadata(engine: dict[str, Any] | None) -> list[str]:
    errors: list[str] = []
    if not isinstance(engine, dict):
        return ["engine missing"]
    if not str(engine.get("name") or "").strip():
        errors.append("engine.name missing")
    if not str(engine.get("version") or "").strip():
        errors.append("engine.version missing")
    config = engine.get("configuration")
    if not isinstance(config, dict):
        errors.append("engine.configuration missing or not an object")
    return errors


def validate_polygon(poly: Any, *, label: str = "polygon") -> list[str]:
    errors: list[str] = []
    if not isinstance(poly, list) or len(poly) < 3:
        return [f"{label}: need >= 3 points"]
    for i, pt in enumerate(poly):
        if not isinstance(pt, (list, tuple)) or len(pt) != 2:
            errors.append(f"{label}[{i}]: need [x,y]")
            continue
        x, y = pt
        if not isinstance(x, (int, float)) or not isinstance(y, (int, float)):
            errors.append(f"{label}[{i}]: non-numeric")
            continue
        if not (0.0 - 1e-6 <= float(x) <= 1.0 + 1e-6 and 0.0 - 1e-6 <= float(y) <= 1.0 + 1e-6):
            errors.append(f"{label}[{i}]: out of [0,1]")
    return errors


def validate_extraction_result(payload: dict[str, Any]) -> list[str]:
    """Lightweight structural validation (does not require jsonschema package)."""
    errors: list[str] = []
    if payload.get("schema_label") != SCHEMA_LABEL:
        errors.append("schema_label must be EVALUATION SCHEMA — NOT YET PRODUCTION CONTRACT")
    errors.extend(validate_engine_metadata(payload.get("engine")))
    doc = payload.get("document")
    if not isinstance(doc, dict):
        errors.append("document missing")
        return errors
    if not str(doc.get("document_id") or "").strip():
        errors.append("document.document_id missing")
    if not str(doc.get("safe_alias") or "").strip():
        errors.append("document.safe_alias missing")
    pages = doc.get("pages")
    if not isinstance(pages, list) or not pages:
        errors.append("document.pages must be a non-empty list")
        return errors
    for pi, page in enumerate(pages):
        if not isinstance(page, dict):
            errors.append(f"pages[{pi}] not an object")
            continue
        if not isinstance(page.get("page_number"), int) or page["page_number"] < 1:
            errors.append(f"pages[{pi}].page_number invalid")
        if page.get("input_layer") not in INPUT_LAYERS:
            errors.append(f"pages[{pi}].input_layer invalid")
        if page.get("canonical_status") not in {"canonical", "rejected", "alternative"}:
            errors.append(f"pages[{pi}].canonical_status invalid")
        regions = page.get("regions")
        if not isinstance(regions, list):
            errors.append(f"pages[{pi}].regions missing")
            continue
        for ri, region in enumerate(regions):
            if not isinstance(region, dict):
                errors.append(f"pages[{pi}].regions[{ri}] invalid")
                continue
            if "reading_order" not in region:
                errors.append(f"pages[{pi}].regions[{ri}].reading_order missing")
            if region.get("polygon") is not None:
                errors.extend(
                    validate_polygon(region["polygon"], label=f"pages[{pi}].regions[{ri}].polygon")
                )
            for li, line in enumerate(region.get("lines") or []):
                if not isinstance(line, dict):
                    continue
                if line.get("polygon") is not None:
                    errors.extend(
                        validate_polygon(
                            line["polygon"],
                            label=f"pages[{pi}].regions[{ri}].lines[{li}].polygon",
                        )
                    )
                for wi, word in enumerate(line.get("words") or []):
                    if not isinstance(word, dict):
                        continue
                    if word.get("polygon") is not None:
                        errors.extend(
                            validate_polygon(
                                word["polygon"],
                                label=(
                                    f"pages[{pi}].regions[{ri}].lines[{li}]."
                                    f"words[{wi}].polygon"
                                ),
                            )
                        )
                    for sym in word.get("symbols") or []:
                        if isinstance(sym, dict) and sym.get("polygon") is not None:
                            # Symbols with fabricated geometry are rejected by invariants elsewhere.
                            errors.extend(
                                validate_polygon(
                                    sym["polygon"],
                                    label="symbol.polygon",
                                )
                            )
    return errors


def assert_valid_extraction_result(payload: dict[str, Any]) -> None:
    errors = validate_extraction_result(payload)
    if errors:
        raise SchemaValidationError("; ".join(errors))


def annotation_eligible_for_soft_metrics(annotation: dict[str, Any]) -> bool:
    status = str(annotation.get("annotation_status") or "")
    return status in APPROVED_FOR_SOFT_METRICS


def validate_annotation(annotation: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    status = annotation.get("annotation_status")
    if status not in ANNOTATION_STATUSES:
        errors.append(f"annotation_status invalid: {status!r}")
    if "page_number" not in annotation:
        errors.append("page_number missing")
    if "expected_transcript" not in annotation and status in APPROVED_FOR_SOFT_METRICS:
        errors.append("expected_transcript required for approved annotations")
    return errors
