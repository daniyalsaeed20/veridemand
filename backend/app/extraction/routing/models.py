"""Internal routing models (not public API contracts)."""

from __future__ import annotations

from dataclasses import dataclass, field

from backend.app.contracts.routing import PageRoute, PageRouteDecision
from backend.app.settings.config import Settings


@dataclass(frozen=True, slots=True)
class RoutingPolicy:
    """Centralised Phase 4.5 routing thresholds (single source of knobs)."""

    version: str
    hybrid_enabled: bool
    embedded_visual_enabled: bool
    embedded_recognition_enabled: bool
    targeted_repair_enabled: bool
    blank_preflight_enabled: bool
    fast_pass_enabled: bool
    min_native_words: int
    min_native_characters: int
    visual_sample_size: int
    recognition_sample_size: int
    min_visible_box_ratio: float
    min_visual_agreement: float
    min_recognition_agreement: float
    max_fail_ratio_for_repair: float
    max_repair_regions: int
    max_repair_coverage: float
    repair_padding_ratio: float
    blank_max_ink_density: float
    blank_max_edge_density: float
    blank_max_variance: float
    visibility_probe_dpi: float
    primary_limit_side: int
    fallback_limit_side: int
    recognition_batch_size: int
    min_candidate_box_coverage: float
    max_ink_outside_candidates_ratio: float
    max_uncovered_textlike_ratio: float
    min_form_line_density_for_coverage_gate: float
    min_checkbox_density_for_coverage_gate: float

    @classmethod
    def from_settings(cls, settings: Settings) -> RoutingPolicy:
        return cls(
            version=settings.page_routing_policy_version,
            hybrid_enabled=settings.hybrid_page_routing_enabled,
            embedded_visual_enabled=settings.embedded_ocr_visual_agreement_enabled,
            embedded_recognition_enabled=settings.embedded_ocr_recognition_check_enabled,
            targeted_repair_enabled=settings.targeted_region_repair_enabled,
            blank_preflight_enabled=settings.blank_page_preflight_enabled,
            fast_pass_enabled=settings.ocr_fast_pass_enabled,
            min_native_words=settings.embedded_ocr_min_native_words,
            min_native_characters=settings.embedded_ocr_min_native_characters,
            visual_sample_size=settings.embedded_ocr_visual_sample_size,
            recognition_sample_size=settings.embedded_ocr_recognition_sample_size,
            min_visible_box_ratio=settings.embedded_ocr_min_visible_box_ratio,
            min_visual_agreement=settings.embedded_ocr_min_visual_agreement,
            min_recognition_agreement=settings.embedded_ocr_min_recognition_agreement,
            max_fail_ratio_for_repair=settings.embedded_ocr_targeted_repair_max_fail_ratio,
            max_repair_regions=settings.embedded_ocr_targeted_repair_max_regions,
            max_repair_coverage=settings.embedded_ocr_targeted_repair_max_coverage,
            repair_padding_ratio=settings.embedded_ocr_repair_padding_ratio,
            blank_max_ink_density=settings.blank_page_max_ink_density,
            blank_max_edge_density=settings.blank_page_max_edge_density,
            blank_max_variance=settings.blank_page_max_variance,
            visibility_probe_dpi=float(settings.ocr_visibility_probe_dpi),
            primary_limit_side=settings.ocr_primary_limit_side_len,
            fallback_limit_side=settings.ocr_fallback_limit_side_len,
            recognition_batch_size=settings.ocr_recognition_batch_size,
            min_candidate_box_coverage=settings.embedded_ocr_min_candidate_box_coverage,
            max_ink_outside_candidates_ratio=settings.embedded_ocr_max_ink_outside_candidates_ratio,
            max_uncovered_textlike_ratio=settings.embedded_ocr_max_uncovered_textlike_ratio,
            min_form_line_density_for_coverage_gate=(
                settings.embedded_ocr_min_form_line_density_for_coverage_gate
            ),
            min_checkbox_density_for_coverage_gate=(
                settings.embedded_ocr_min_checkbox_density_for_coverage_gate
            ),
        )


@dataclass(slots=True)
class VisualAgreementMetrics:
    """Aggregate visual-agreement metrics (no text)."""

    sampled_box_count: int = 0
    visible_box_ratio: float = 0.0
    blank_box_ratio: float = 0.0
    out_of_bounds_ratio: float = 0.0
    mean_variance: float = 0.0
    mean_edge_density: float = 0.0
    mean_contrast: float = 0.0
    spatial_coverage: float = 0.0
    visual_agreement_score: float = 0.0
    failed_box_indices: list[int] = field(default_factory=list)
    reason_codes: list[str] = field(default_factory=list)


@dataclass(slots=True)
class RecognitionAgreementMetrics:
    """Aggregate recognition spot-check metrics (no sample strings)."""

    sample_count: int = 0
    character_agreement: float = 0.0
    token_agreement: float = 0.0
    numeric_token_agreement: float = 0.0
    mean_recognition_confidence: float = 0.0
    recognition_agreement_score: float = 0.0
    failed_sample_indices: list[int] = field(default_factory=list)
    reason_codes: list[str] = field(default_factory=list)


@dataclass(slots=True)
class RouteExecutionPlan:
    """What the visual pipeline should do after a route decision."""

    decision: PageRouteDecision
    skip_full_ocr: bool
    retain_native_text: bool
    use_embedded_authority: bool
    run_targeted_repair: bool
    run_full_ocr: bool
    run_blank_preflight: bool

    @property
    def route(self) -> PageRoute:
        return self.decision.route
