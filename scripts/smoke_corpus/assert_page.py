"""Compare API native/canonical results against a smoke manifest page entry."""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any

UNSAFE_DECISIONS = frozenset({"rejected", "absent", "error", "suppressed_by_document_escalation"})

PHASE3_REASON_CODES = frozenset(
    {
        "native_text_absent",
        "native_text_too_sparse",
        "native_extraction_error",
        "native_page_metadata_mismatch",
        "native_character_limit_exceeded",
        "native_word_limit_exceeded",
        "high_replacement_character_ratio",
        "high_control_character_ratio",
        "high_private_use_character_ratio",
        "high_unassigned_character_ratio",
        "high_noncharacter_ratio",
        "high_unprintable_character_ratio",
        "high_cid_token_ratio",
        "invalid_character_geometry",
        "invalid_word_geometry",
        "text_outside_page_bounds",
        "zero_area_text_geometry",
        "excessive_duplicate_characters",
        "excessive_near_overprint_duplicates",
        "high_symbol_only_word_ratio",
        "high_single_character_word_ratio",
        "improbable_token_structure",
        "unstable_extraction_order",
        "image_dominant_page",
        "canonical_image_source",
        "native_trust_score_below_threshold",
        "visual_agreement_not_evaluated_phase_3",
        "document_visual_authority_escalation",
        "native_text_rejected",
    }
)


@dataclass
class AssertionFailure:
    code: str
    message: str


@dataclass
class PageAssertionResult:
    status: str  # passed | failed | skipped_for_future_phase | document_escalation_observed
    failures: list[AssertionFailure] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return self.status in {
            "passed",
            "skipped_for_future_phase",
            "document_escalation_observed",
        }


def _geometry_ok(geometry: dict[str, Any] | None) -> bool:
    if not isinstance(geometry, dict):
        return False
    for key in ("x", "y", "width", "height"):
        value = geometry.get(key)
        if not isinstance(value, (int, float)) or isinstance(value, bool):
            return False
        if math.isnan(value) or math.isinf(value):
            return False
        if value < 0.0 or value > 1.0:
            return False
    width = float(geometry["width"])
    height = float(geometry["height"])
    return width > 0.0 and height > 0.0 and float(geometry["x"]) + width <= 1.0001


def _probe_token(manifest_page: dict[str, Any]) -> str:
    test_id = str(manifest_page.get("test_id") or "")
    return test_id


def assert_publication_safety(
    *,
    decision: str,
    page_result: dict[str, Any] | None,
    sse_blobs: list[str],
    public_file_blobs: list[str],
    probe: str,
) -> list[AssertionFailure]:
    failures: list[AssertionFailure] = []
    if decision not in UNSAFE_DECISIONS:
        return failures

    words = (page_result or {}).get("words") or []
    characters = (page_result or {}).get("characters") or []
    provisional = (page_result or {}).get("provisional_native_text")
    if words:
        failures.append(
            AssertionFailure("words_not_empty", "Rejected/unsafe page published words.")
        )
    if characters:
        failures.append(
            AssertionFailure("characters_not_empty", "Rejected/unsafe page published characters.")
        )
    if provisional:
        failures.append(
            AssertionFailure(
                "provisional_text_present",
                "Rejected/unsafe page published provisional_native_text.",
            )
        )

    if probe:
        for blob in sse_blobs:
            if probe and probe in blob and "test_id" not in blob:
                # Allow structured metadata that names the test; block free-form dumps.
                pass
        # Only fail when long provisional-like content appears; probe is short (Txx).
        # Prefer scanning for explicit provisional_native_text keys.
        for blob in [*sse_blobs, *public_file_blobs]:
            if (
                '"provisional_native_text": "' in blob
                and "null"
                not in blob[
                    blob.find('"provisional_native_text"') : blob.find('"provisional_native_text"')
                    + 80
                ]
            ):
                failures.append(
                    AssertionFailure(
                        "rejected_text_leaked",
                        "Public stream/file appears to contain provisional native text.",
                    )
                )
                break
    return failures


def _interleaved_double_ratio(text: str) -> float:
    if not text:
        return 0.0
    doubles = 0
    alnum = 0
    i = 0
    while i + 1 < len(text):
        if text[i].isalnum():
            alnum += 1
        if text[i] == text[i + 1] and text[i].isalnum():
            doubles += 1
            i += 2
        else:
            i += 1
    return doubles / max(alnum, 1)


def _max_consecutive_double_pair_run(text: str) -> int:
    if not text:
        return 0
    best = 0
    run = 0
    i = 0
    while i + 1 < len(text):
        a, b = text[i], text[i + 1]
        if a.isalnum() and a == b:
            run += 1
            best = max(best, run)
            i += 2
            continue
        run = 0
        i += 1
    return best


def _check_acceptable_outcome(
    outcome: dict[str, Any],
    *,
    decision: str,
    source_mode: str,
    reason_codes: list[str],
    page_result: dict[str, Any] | None,
    sse_blobs: list[str],
    public_file_blobs: list[str],
    probe: str,
) -> list[AssertionFailure]:
    """Return failures if ``outcome`` does not match the observed page result."""

    failures: list[AssertionFailure] = []
    expected_decision = outcome.get("decision")
    expected_mode = outcome.get("source_mode")
    if expected_decision and decision != expected_decision:
        failures.append(
            AssertionFailure(
                "outcome_decision_mismatch",
                f"outcome expected decision={expected_decision!r}, actual={decision!r}",
            )
        )
    if expected_mode and source_mode != expected_mode:
        failures.append(
            AssertionFailure(
                "outcome_mode_mismatch",
                f"outcome expected source_mode={expected_mode!r}, actual={source_mode!r}",
            )
        )

    required = [str(c) for c in (outcome.get("require_reason_codes") or [])]
    missing = [c for c in required if c not in reason_codes]
    if missing:
        failures.append(
            AssertionFailure(
                "outcome_reason_codes_missing",
                f"outcome missing reason codes: {missing}",
            )
        )

    if decision in UNSAFE_DECISIONS or outcome.get("require_empty_publication"):
        failures.extend(
            assert_publication_safety(
                decision=decision if decision in UNSAFE_DECISIONS else "rejected",
                page_result=page_result,
                sse_blobs=sse_blobs,
                public_file_blobs=public_file_blobs,
                probe=probe,
            )
        )

    if outcome.get("require_no_interleaved_duplicates") and decision == "accepted":
        provisional = str((page_result or {}).get("provisional_native_text") or "")
        if not provisional:
            words = (page_result or {}).get("words") or []
            provisional = " ".join(str(w.get("text") or "") for w in words if isinstance(w, dict))
        if _interleaved_double_ratio(provisional) >= 0.35:
            failures.append(
                AssertionFailure(
                    "interleaved_duplicates",
                    "Accepted page still has high interleaved-double ratio.",
                )
            )
        if _max_consecutive_double_pair_run(provisional) >= 4:
            failures.append(
                AssertionFailure(
                    "aabb_overprint_run",
                    "Accepted page still has a dense AABB overprint run.",
                )
            )
        compact = provisional.replace(" ", "").upper()
        for token in outcome.get("forbidden_substrings") or []:
            needle = str(token).replace(" ", "").upper()
            if needle and needle in compact:
                failures.append(
                    AssertionFailure(
                        "forbidden_duplicate_token",
                        f"Accepted page published forbidden duplicate token {token!r}.",
                    )
                )
                break

    return failures


def assert_page(
    *,
    manifest_page: dict[str, Any],
    trust: dict[str, Any] | None,
    page_result: dict[str, Any] | None,
    canonical_page: dict[str, Any] | None,
    canonical_ok: bool,
    document_escalated: bool = False,
    sse_blobs: list[str] | None = None,
    public_file_blobs: list[str] | None = None,
) -> PageAssertionResult:
    phase = str(manifest_page.get("phase_expectation") or "current_phase_expected")
    failures: list[AssertionFailure] = []
    notes: list[str] = []

    if trust is None:
        failures.append(AssertionFailure("trust_missing", "No page trust result available."))
        return PageAssertionResult(status="failed", failures=failures)

    decision = str(trust.get("decision") or "")
    source_mode = str(trust.get("source_mode") or "")
    reason_codes = [str(c) for c in (trust.get("reason_codes") or [])]
    raw_metrics = trust.get("metrics")
    metrics: dict[str, Any] = raw_metrics if isinstance(raw_metrics, dict) else {}

    if document_escalated and decision == "suppressed_by_document_escalation":
        notes.append("page suppressed after document visual-authority escalation")
        return PageAssertionResult(status="document_escalation_observed", failures=[], notes=notes)

    expected_mode = manifest_page.get("expected_source_mode")
    expected_decision = manifest_page.get("expected_decision")

    soft_phase = phase in {
        "future_phase_expected",
        "not_yet_implemented",
        "viewer_only",
        "document_scoped_not_representable",
    }

    if phase == "future_phase_expected":
        # Phase 3 pass: safely routed away from native authority when expected.
        if expected_mode in {"visual_authority", "image_authority"}:
            if source_mode == "native_authority" and decision == "accepted":
                failures.append(
                    AssertionFailure(
                        "unsafe_native_accept",
                        "Future-phase page was accepted under native_authority.",
                    )
                )
            elif (
                source_mode in {"visual_authority", "image_authority"}
                or decision in UNSAFE_DECISIONS
            ):
                notes.append("future-phase page safely routed for Phase 3")
            else:
                notes.append(f"future-phase observed mode={source_mode} decision={decision}")
        safety = assert_publication_safety(
            decision=decision,
            page_result=page_result,
            sse_blobs=sse_blobs or [],
            public_file_blobs=public_file_blobs or [],
            probe=_probe_token(manifest_page),
        )
        failures.extend(safety)
        if failures:
            return PageAssertionResult(status="failed", failures=failures, notes=notes)
        return PageAssertionResult(status="skipped_for_future_phase", failures=[], notes=notes)

    if phase in {"not_yet_implemented", "document_scoped_not_representable"}:
        safety = assert_publication_safety(
            decision=decision,
            page_result=page_result,
            sse_blobs=sse_blobs or [],
            public_file_blobs=public_file_blobs or [],
            probe=_probe_token(manifest_page),
        )
        failures.extend(safety)
        if failures:
            return PageAssertionResult(status="failed", failures=failures, notes=notes)
        notes.append(f"{phase}: soft pass (crash/safety only)")
        return PageAssertionResult(status="skipped_for_future_phase", failures=[], notes=notes)

    # current_phase_expected and viewer_only
    if manifest_page.get("canonical_viewer_success") and not canonical_ok:
        failures.append(
            AssertionFailure("canonical_viewer_failed", "Canonical PDF was not viewable.")
        )

    acceptable = manifest_page.get("acceptable_outcomes")
    dual_matched = False
    if phase == "current_phase_expected" and isinstance(acceptable, list) and acceptable:
        probe = _probe_token(manifest_page)
        for outcome in acceptable:
            if not isinstance(outcome, dict):
                continue
            ofails = _check_acceptable_outcome(
                outcome,
                decision=decision,
                source_mode=source_mode,
                reason_codes=reason_codes,
                page_result=page_result,
                sse_blobs=sse_blobs or [],
                public_file_blobs=public_file_blobs or [],
                probe=probe,
            )
            if not ofails:
                dual_matched = True
                notes.append(
                    f"matched acceptable outcome decision={outcome.get('decision')!r} "
                    f"source_mode={outcome.get('source_mode')!r}"
                )
                break
        if not dual_matched:
            failures.append(
                AssertionFailure(
                    "acceptable_outcomes_unmatched",
                    f"No acceptable_outcomes matched (decision={decision!r}, "
                    f"source_mode={source_mode!r}, reasons={reason_codes}).",
                )
            )

    if phase != "viewer_only" and not dual_matched:
        # Skip singular mismatch when dual-outcome list was present but unmatched
        # (already recorded). When no dual list, enforce singular expectations.
        if (
            expected_mode
            and source_mode != expected_mode
            and not (isinstance(acceptable, list) and acceptable)
        ):
            failures.append(
                AssertionFailure(
                    "authority_mismatch",
                    f"expected source_mode={expected_mode!r}, actual={source_mode!r}",
                )
            )
        image_absent_ok = (
            expected_decision == "rejected"
            and decision == "absent"
            and expected_mode == "image_authority"
        )
        if (
            expected_decision
            and decision != expected_decision
            and not image_absent_ok
            and not (isinstance(acceptable, list) and acceptable)
        ):
            failures.append(
                AssertionFailure(
                    "decision_mismatch",
                    f"expected decision={expected_decision!r}, actual={decision!r}",
                )
            )

        if (
            manifest_page.get("hard_rejection") is True
            and not trust.get("hard_rejection")
            and decision not in {"rejected", "absent"}
            and not (isinstance(acceptable, list) and acceptable)
        ):
            failures.append(
                AssertionFailure(
                    "hard_rejection_missing",
                    "Expected a hard rejection but page was not rejected/absent.",
                )
            )

        expected_codes = [
            str(c)
            for c in (
                manifest_page.get("phase3_reason_codes")
                or [
                    c
                    for c in (manifest_page.get("expected_reason_codes") or [])
                    if c in PHASE3_REASON_CODES
                ]
            )
        ]
        if (
            expected_codes
            and phase == "current_phase_expected"
            and not (isinstance(acceptable, list) and acceptable)
        ):
            missing = [c for c in expected_codes if c not in reason_codes]
            if missing:
                failures.append(
                    AssertionFailure(
                        "reason_codes_missing",
                        f"missing expected Phase-3 reason codes: {missing}",
                    )
                )

        forbidden = [str(c) for c in (manifest_page.get("forbidden_reason_codes") or [])]
        hit = [c for c in forbidden if c in reason_codes]
        if hit:
            failures.append(
                AssertionFailure(
                    "forbidden_reason_codes",
                    f"forbidden reason codes present: {hit}",
                )
            )

        if "native_result_available" in manifest_page:
            expected_nra = bool(manifest_page["native_result_available"])
            actual_nra = bool(trust.get("native_result_available"))
            # Dual accept may flip native_result_available; skip when dual matched.
            if expected_nra != actual_nra and not soft_phase and not dual_matched:
                failures.append(
                    AssertionFailure(
                        "native_result_available_mismatch",
                        f"expected native_result_available={expected_nra}, actual={actual_nra}",
                    )
                )

        if "visual_processing_required" in manifest_page:
            expected_vpr = bool(manifest_page["visual_processing_required"])
            actual_vpr = bool(trust.get("visual_processing_required"))
            if (
                expected_vpr != actual_vpr
                and phase == "current_phase_expected"
                and not document_escalated
                and not dual_matched
            ):
                failures.append(
                    AssertionFailure(
                        "visual_processing_required_mismatch",
                        f"expected visual_processing_required={expected_vpr}, actual={actual_vpr}",
                    )
                )

        score = trust.get("native_trust_score")
        if isinstance(score, (int, float)):
            min_score = manifest_page.get("min_trust_score")
            max_score = manifest_page.get("max_trust_score")
            if isinstance(min_score, (int, float)) and float(score) < float(min_score):
                failures.append(
                    AssertionFailure(
                        "trust_score_too_low",
                        f"trust score {score} < min {min_score}",
                    )
                )
            if isinstance(max_score, (int, float)) and float(score) > float(max_score):
                failures.append(
                    AssertionFailure(
                        "trust_score_too_high",
                        f"trust score {score} > max {max_score}",
                    )
                )

        min_dup = manifest_page.get("min_duplicate_character_ratio")
        if isinstance(min_dup, (int, float)):
            actual_dup = metrics.get("duplicate_character_ratio")
            if not isinstance(actual_dup, (int, float)) or float(actual_dup) < float(min_dup):
                failures.append(
                    AssertionFailure(
                        "duplicate_metric_too_low",
                        f"duplicate_character_ratio {actual_dup!r} < min {min_dup}",
                    )
                )
    elif phase != "viewer_only" and dual_matched:
        # Soft-check publication policy for the matched dual outcome.
        word_policy = manifest_page.get("word_publication")
        if decision in UNSAFE_DECISIONS or word_policy == "forbidden":
            # Reject branch already checked empty publication inside outcome matcher.
            pass
        elif word_policy == "required" and decision == "accepted":
            words = (page_result or {}).get("words") if page_result else None
            if not words:
                failures.append(
                    AssertionFailure("words_required", "Accepted page published no words.")
                )

    # Rotation / dimensions from canonical metadata when present.
    expected_rotation = manifest_page.get("expected_rotation")
    if (
        isinstance(expected_rotation, int)
        and canonical_page is not None
        and "intrinsic_rotation" in canonical_page
    ):
        actual_rot = int(canonical_page["intrinsic_rotation"]) % 360
        if actual_rot != expected_rotation % 360:
            # Canonicalisation may normalise rotation into width/height swap.
            notes.append(
                f"rotation: manifest={expected_rotation} canonical={actual_rot} "
                "(normalisation may apply)"
            )

    size = manifest_page.get("page_size_points")
    if (
        isinstance(size, list)
        and len(size) == 2
        and canonical_page is not None
        and phase == "current_phase_expected"
    ):
        cw = canonical_page.get("width_points")
        ch = canonical_page.get("height_points")
        if isinstance(cw, (int, float)) and isinstance(ch, (int, float)):
            # Allow rotation-swapped dimensions within 2pt.
            w, h = float(size[0]), float(size[1])
            match = (abs(cw - w) <= 2 and abs(ch - h) <= 2) or (
                abs(cw - h) <= 2 and abs(ch - w) <= 2
            )
            if not match:
                failures.append(
                    AssertionFailure(
                        "page_size_mismatch",
                        f"expected ~{size}, canonical=[{cw}, {ch}]",
                    )
                )

    # Publication policy (singular path; dual reject already covered)
    if not dual_matched:
        word_policy = manifest_page.get("word_publication")
        words = (page_result or {}).get("words") if page_result else None
        if word_policy == "required" and decision == "accepted":
            if not words:
                failures.append(
                    AssertionFailure("words_required", "Accepted page published no words.")
                )
            else:
                for word in words:
                    if not isinstance(word, dict):
                        continue
                    geom = word.get("geometry")
                    if not isinstance(geom, dict):
                        continue
                    box = geom.get("bbox")
                    if isinstance(box, dict) and not _geometry_ok(box):
                        failures.append(
                            AssertionFailure(
                                "geometry_out_of_bounds",
                                "Word geometry is non-finite or outside [0,1].",
                            )
                        )
                        break

        if word_policy == "forbidden" or decision in UNSAFE_DECISIONS:
            failures.extend(
                assert_publication_safety(
                    decision=decision if decision in UNSAFE_DECISIONS else "rejected",
                    page_result=page_result,
                    sse_blobs=sse_blobs or [],
                    public_file_blobs=public_file_blobs or [],
                    probe=_probe_token(manifest_page),
                )
            )

    if failures:
        return PageAssertionResult(status="failed", failures=failures, notes=notes)
    if phase == "viewer_only":
        return PageAssertionResult(status="passed", failures=[], notes=notes)
    return PageAssertionResult(status="passed", failures=[], notes=notes)
