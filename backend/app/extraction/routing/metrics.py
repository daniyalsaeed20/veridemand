"""Privacy-safe routing metrics helpers."""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger("veridemand.routing.metrics")


def log_page_route_decision(
    *,
    document_id: str,
    page_number: int,
    route: str,
    reason_codes: list[str],
    native_word_count: int,
    visual_agreement_score: float | None,
    sample_count: int,
    recognition_agreement_score: float | None,
    full_ocr_required: bool,
    primary_limit_side: int | None = None,
    fallback_used: bool | None = None,
    route_duration_ms: int | None = None,
    render_duration_ms: int | None = None,
    ocr_duration_ms: int | None = None,
    page_total_duration_ms: int | None = None,
    policy_version: str | None = None,
    proposed_route: str | None = None,
    final_route: str | None = None,
    native_candidate_available: bool | None = None,
    native_trust_score: float | None = None,
    replacement_character_ratio: float | None = None,
    control_character_ratio: float | None = None,
    private_use_character_ratio: float | None = None,
    unassigned_character_ratio: float | None = None,
    symbol_character_ratio: float | None = None,
    quarantined_glyph_count: int | None = None,
    quarantined_region_count: int | None = None,
    glyph_materiality: str | None = None,
    document_escalation_applied: bool | None = None,
    page_restored_after_escalation: bool | None = None,
    visual_agreement_evaluated: bool | None = None,
    recognition_check_evaluated: bool | None = None,
    targeted_repair_eligible: bool | None = None,
    failed_rule: str | None = None,
    decision_duration_ms: int | None = None,
) -> None:
    """Log a page route decision without text, paths, or filenames."""

    extra: dict[str, Any] = {
        "event": "page_route_decision",
        "document_id": document_id,
        "page_number": page_number,
        "policy_version": policy_version,
        "proposed_route": proposed_route or route,
        "final_route": final_route or route,
        "route": route,
        "reason_codes": list(reason_codes),
        "native_candidate_available": native_candidate_available,
        "native_word_count": native_word_count,
        "native_trust_score": native_trust_score,
        "replacement_character_ratio": replacement_character_ratio,
        "control_character_ratio": control_character_ratio,
        "private_use_character_ratio": private_use_character_ratio,
        "unassigned_character_ratio": unassigned_character_ratio,
        "symbol_character_ratio": symbol_character_ratio,
        "quarantined_glyph_count": quarantined_glyph_count,
        "quarantined_region_count": quarantined_region_count,
        "glyph_materiality": glyph_materiality,
        "document_escalation_applied": document_escalation_applied,
        "page_restored_after_escalation": page_restored_after_escalation,
        "visual_agreement_evaluated": visual_agreement_evaluated,
        "visual_agreement_score": visual_agreement_score,
        "recognition_check_evaluated": recognition_check_evaluated,
        "sample_count": sample_count,
        "recognition_agreement_score": recognition_agreement_score,
        "targeted_repair_eligible": targeted_repair_eligible,
        "full_ocr_required": full_ocr_required,
        "failed_rule": failed_rule,
        "primary_limit_side": primary_limit_side,
        "fallback_used": fallback_used,
        "route_duration_ms": route_duration_ms,
        "decision_duration_ms": decision_duration_ms
        if decision_duration_ms is not None
        else route_duration_ms,
        "render_duration_ms": render_duration_ms,
        "ocr_duration_ms": ocr_duration_ms,
        "page_total_duration_ms": page_total_duration_ms,
    }
    logger.info("page_route_decision", extra=extra)


def log_duplicate_layer_decision(
    *,
    document_id: str,
    page_number: int,
    policy_version: str,
    strict_duplicate_ratio: float,
    near_overprint_duplicate_ratio: float,
    duplicate_layer_coverage_ratio: float,
    matched_near_duplicate_count: int,
    duplicate_line_count: int,
    duplicate_region_count: int,
    offset_cluster_count: int,
    path_a_satisfied: bool,
    path_b_satisfied: bool,
    selected_path: str,
    duplicate_hard_rejection: bool,
    overall_native_hard_rejection: bool,
    overall_rejection_reason_codes: list[str],
    final_page_route: str | None,
    decision_duration_ms: int | None,
) -> None:
    """Log a duplicate-layer decision without text, filenames, or private paths."""

    extra: dict[str, Any] = {
        "event": "duplicate_layer_decision",
        "document_id": document_id,
        "page_number": page_number,
        "policy_version": policy_version,
        "strict_duplicate_ratio": strict_duplicate_ratio,
        "near_overprint_duplicate_ratio": near_overprint_duplicate_ratio,
        "duplicate_layer_coverage_ratio": duplicate_layer_coverage_ratio,
        "matched_near_duplicate_count": matched_near_duplicate_count,
        "duplicate_line_count": duplicate_line_count,
        "duplicate_region_count": duplicate_region_count,
        "offset_cluster_count": offset_cluster_count,
        "path_a_satisfied": path_a_satisfied,
        "path_b_satisfied": path_b_satisfied,
        "selected_path": selected_path,
        "duplicate_hard_rejection": duplicate_hard_rejection,
        "overall_native_hard_rejection": overall_native_hard_rejection,
        "overall_rejection_reason_codes": list(overall_rejection_reason_codes),
        "final_page_route": final_page_route,
        "decision_duration_ms": decision_duration_ms,
    }
    logger.info("duplicate_layer_decision", extra=extra)


def log_document_routing_summary(
    *,
    document_id: str,
    document_pages_total: int,
    digital_native_pages: int,
    embedded_verified_pages: int,
    targeted_repair_pages: int,
    full_ocr_pages: int,
    no_text_pages: int,
    failed_pages: int,
) -> None:
    """Log document-level routing counts without private content."""

    extra: dict[str, Any] = {
        "event": "document_routing_summary",
        "document_id": document_id,
        "document_pages_total": document_pages_total,
        "digital_native_pages": digital_native_pages,
        "embedded_verified_pages": embedded_verified_pages,
        "targeted_repair_pages": targeted_repair_pages,
        "full_ocr_pages": full_ocr_pages,
        "no_text_pages": no_text_pages,
        "failed_pages": failed_pages,
    }
    logger.info("document_routing_summary", extra=extra)
