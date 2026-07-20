"""Score an engine extraction result against an annotation."""

from __future__ import annotations

from typing import Any

from .metrics_critical import score_critical_fields
from .metrics_geometry import compute_geometry_metrics
from .metrics_layers import score_layer_selection, score_safe_failure
from .metrics_order import compute_order_metrics
from .metrics_text import compute_text_metrics
from .schema import (
    SchemaValidationError,
    annotation_eligible_for_soft_metrics,
    validate_annotation,
    validate_extraction_result,
)


def _collect_polygons(result: dict[str, Any]) -> list[list[list[float]]]:
    polys: list[list[list[float]]] = []
    for page in result.get("document", {}).get("pages") or []:
        for region in page.get("regions") or []:
            if region.get("polygon"):
                polys.append(region["polygon"])
            for line in region.get("lines") or []:
                if line.get("polygon"):
                    polys.append(line["polygon"])
                for word in line.get("words") or []:
                    if word.get("polygon"):
                        polys.append(word["polygon"])
                    for sym in word.get("symbols") or []:
                        if sym.get("polygon"):
                            polys.append(sym["polygon"])
    return polys


def _page_text(result: dict[str, Any], page_number: int) -> tuple[str, list[str], list[str]]:
    lines_out: list[str] = []
    word_ids: list[str] = []
    for page in result.get("document", {}).get("pages") or []:
        if page.get("page_number") != page_number:
            continue
        for region in sorted(page.get("regions") or [], key=lambda r: r.get("reading_order", 0)):
            for line in sorted(region.get("lines") or [], key=lambda ln: ln.get("reading_order", 0)):
                lines_out.append(str(line.get("text") or ""))
                for word in sorted(line.get("words") or [], key=lambda w: w.get("reading_order", 0)):
                    word_ids.append(str(word.get("word_id") or word.get("text") or ""))
    return "\n".join(lines_out), lines_out, word_ids


def _source_link_errors(result: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    doc_id = result.get("document", {}).get("document_id")
    for page in result.get("document", {}).get("pages") or []:
        pn = page.get("page_number")
        for region in page.get("regions") or []:
            rid = region.get("region_id")
            for line in region.get("lines") or []:
                for word in line.get("words") or []:
                    # Words implicitly belong to page/region; flag if empty ids
                    if not word.get("word_id"):
                        errors.append(f"page {pn}: word missing word_id")
                    if not rid:
                        errors.append(f"page {pn}: word without region_id")
        # Cross-doc check placeholder: words must not carry foreign document_id fields
        for region in page.get("regions") or []:
            for line in region.get("lines") or []:
                for word in line.get("words") or []:
                    foreign = word.get("document_id")
                    if foreign and foreign != doc_id:
                        errors.append(f"cross-document reference: {foreign}")
    return errors


def score_engine_against_annotation(
    result: dict[str, Any],
    annotation: dict[str, Any],
) -> dict[str, Any]:
    schema_errors = validate_extraction_result(result)
    ann_errors = validate_annotation(annotation)
    if schema_errors:
        return {
            "ok": False,
            "error": "invalid_engine_result",
            "schema_errors": schema_errors,
            "excluded_from_acceptance": True,
        }
    if ann_errors:
        return {
            "ok": False,
            "error": "invalid_annotation",
            "annotation_errors": ann_errors,
            "excluded_from_acceptance": True,
        }

    if not annotation_eligible_for_soft_metrics(annotation):
        return {
            "ok": True,
            "excluded_from_acceptance": True,
            "reason": "annotation_not_approved",
            "annotation_status": annotation.get("annotation_status"),
            "source_link_errors": _source_link_errors(result),
            "geometry": compute_geometry_metrics(_collect_polygons(result)).as_dict(),
        }

    page_number = int(annotation["page_number"])
    hyp_text, hyp_lines, hyp_word_ids = _page_text(result, page_number)
    ref_text = str(annotation.get("expected_transcript") or "")
    ref_lines = annotation.get("expected_lines") or ref_text.splitlines()
    ref_word_ids = annotation.get("expected_word_ids") or []

    text = compute_text_metrics(
        ref_text,
        hyp_text,
        reference_lines=list(ref_lines),
        hypothesis_lines=hyp_lines,
        compute_cer=bool(annotation.get("has_character_ground_truth")),
    )
    order = compute_order_metrics(
        list(annotation.get("expected_line_ids") or [str(i) for i in range(len(ref_lines))]),
        [str(i) for i in range(len(hyp_lines))],
        list(ref_word_ids) if ref_word_ids else None,
        hyp_word_ids if ref_word_ids else None,
        expected_table_cells=annotation.get("expected_table_cells"),
        actual_table_cells=annotation.get("actual_table_cells"),
        expected_label_values=[tuple(p) for p in annotation.get("expected_label_values") or []],
        actual_label_values=[tuple(p) for p in annotation.get("actual_label_values") or []],
    )
    geom = compute_geometry_metrics(
        _collect_polygons(result),
        paired_reference_polygons=annotation.get("expected_polygons"),
        declared_rotation=(result.get("document", {}).get("pages") or [{}])[0].get("rotation"),
        expected_rotation=annotation.get("expected_rotation"),
    )

    page0 = (result.get("document", {}).get("pages") or [{}])[0]
    layer_pages = [
        {
            "expected_layer": annotation.get("expected_layer"),
            "selected_layer": page0.get("input_layer"),
            "corrupt_embedded": annotation.get("corrupt_embedded", False),
            "must_reject_corrupt": annotation.get("must_reject_corrupt", False),
            "native_trustworthy": annotation.get("native_trustworthy", False),
            "fresh_ocr_ran": annotation.get("fresh_ocr_ran", False),
            "ocr_required": annotation.get("ocr_required", False),
            "silent_mix": annotation.get("silent_mix", False),
            "accepted_as_canonical": page0.get("canonical_status") == "canonical",
        }
    ]
    layers = score_layer_selection(layer_pages)
    safe = score_safe_failure(
        [
            {
                "expected_outcome": annotation.get("expected_outcome"),
                "actual_outcome": page0.get("outcome"),
                "unsafe_usable": annotation.get("unsafe_usable", False),
                "disputed_critical_count": annotation.get("disputed_critical_count", 0),
                "flagged_review_count": annotation.get("flagged_review_count", 0),
            }
        ]
    )
    critical = score_critical_fields(list(annotation.get("critical_fields") or []))

    # Fabricated character geometry invariant
    fabricated_chars = 0
    for page in result.get("document", {}).get("pages") or []:
        for region in page.get("regions") or []:
            for line in region.get("lines") or []:
                for word in line.get("words") or []:
                    for sym in word.get("symbols") or []:
                        if sym.get("polygon") and not annotation.get("has_character_ground_truth"):
                            # Engine claiming symbols without capability flag on annotation side
                            if not result.get("engine", {}).get("configuration", {}).get(
                                "supports_character_geometry"
                            ):
                                fabricated_chars += 1

    return {
        "ok": True,
        "excluded_from_acceptance": False,
        "text": text.as_dict(),
        "order": order.as_dict(),
        "geometry": geom.as_dict(),
        "layers": layers.as_dict(),
        "safe_failure": safe.as_dict(),
        "critical_fields": critical.as_dict(),
        "source_link_errors": _source_link_errors(result),
        "fabricated_character_box_count": fabricated_chars,
        "duplicate_text_layer_rate": float(annotation.get("duplicate_text_layer_rate") or 0.0),
    }


def require_valid_or_raise(result: dict[str, Any]) -> None:
    errors = validate_extraction_result(result)
    if errors:
        raise SchemaValidationError("; ".join(errors))
