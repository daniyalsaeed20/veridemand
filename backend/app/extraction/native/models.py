"""Internal models and policy configuration for native extraction."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass(frozen=True, slots=True)
class NativeTrustPolicyConfig:
    """Serializable trust-policy knobs passed to the worker."""

    native_trust_threshold: float = 0.75
    document_visual_authority_failure_ratio: float = 0.30
    native_dedupe_tolerance_points: float = 1.0
    native_coordinate_tolerance_points: float = 0.5
    native_min_characters: int = 8
    native_max_characters_per_page: int = 250_000
    native_max_words_per_page: int = 100_000
    native_max_replacement_ratio: float = 0.005
    native_max_control_ratio: float = 0.002
    native_max_private_use_ratio: float = 0.005
    native_max_unassigned_ratio: float = 0.005
    native_max_cid_token_ratio: float = 0.05
    native_max_invalid_geometry_ratio: float = 0.01
    native_max_out_of_bounds_ratio: float = 0.01
    native_max_duplicate_ratio: float = 0.20
    native_max_near_overprint_ratio: float = 0.08
    native_max_duplicate_layer_coverage_ratio: float = 0.70
    native_min_near_duplicate_match_count: int = 24
    native_min_dominant_offset_support_ratio: float = 0.55  # informational only
    native_near_overprint_iou_threshold: float = 0.35
    native_near_overprint_centre_factor: float = 0.35
    native_near_overprint_centre_cap_points: float = 3.5
    native_near_overprint_size_similarity: float = 0.40
    native_offset_cluster_abs_tol: float = 0.75
    native_offset_cluster_size_factor: float = 0.08
    native_offset_cluster_top_k: int = 3
    native_path_b_min_coverage: float = 0.90
    native_path_b_min_matches: int = 48
    native_path_b_min_duplicate_lines: int = 2
    native_path_b_min_duplicate_regions: int = 1
    native_region_min_chars: int = 12
    native_region_severe_ratio: float = 0.50
    native_region_min_matched: int = 8
    native_max_symbol_only_word_ratio: float = 0.40
    native_max_single_character_word_ratio: float = 0.75
    native_image_dominant_area_ratio: float = 0.80
    native_document_min_failed_pages: int = 2
    native_trust_policy_version: str = "phase3-v1.6"
    canonical_page_dimension_tolerance_points: float = 0.5
    native_extraction_test_delay_seconds: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> NativeTrustPolicyConfig:
        known = {f.name for f in cls.__dataclass_fields__.values()}
        return cls(**{k: v for k, v in data.items() if k in known})


@dataclass(frozen=True, slots=True)
class CanonicalPageRef:
    """Canonical page metadata required by the worker."""

    page_number: int
    width_points: float
    height_points: float
    intrinsic_rotation: int
    source_type: str


@dataclass(frozen=True, slots=True)
class NativeWorkerRequest:
    """Request payload written to staging for the native worker."""

    session_id: str
    document_id: str
    job_id: str
    canonical_pdf_path: str
    canonicalisation_method: str
    pages: list[CanonicalPageRef]
    policy: NativeTrustPolicyConfig
    self_check: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "session_id": self.session_id,
            "document_id": self.document_id,
            "job_id": self.job_id,
            "canonical_pdf_path": self.canonical_pdf_path,
            "canonicalisation_method": self.canonicalisation_method,
            "pages": [asdict(p) for p in self.pages],
            "policy": self.policy.to_dict(),
            "self_check": self.self_check,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> NativeWorkerRequest:
        pages = [CanonicalPageRef(**p) for p in data["pages"]]
        return cls(
            session_id=data["session_id"],
            document_id=data["document_id"],
            job_id=data["job_id"],
            canonical_pdf_path=data["canonical_pdf_path"],
            canonicalisation_method=data["canonicalisation_method"],
            pages=pages,
            policy=NativeTrustPolicyConfig.from_dict(data["policy"]),
            self_check=bool(data.get("self_check", False)),
        )


@dataclass(slots=True)
class RawCharCandidate:
    """Candidate character before trust publication."""

    text: str
    fontname: str | None
    size: float
    upright: bool
    rotation_degrees: float
    x0: float
    x1: float
    top: float
    bottom: float
    sequence_index: int
    tagged: bool | None = None


@dataclass(slots=True)
class RawWordCandidate:
    """Candidate word before trust publication."""

    text: str
    x0: float
    x1: float
    top: float
    bottom: float
    sequence_index: int
    char_indices: list[int] = field(default_factory=list)
    fontnames: list[str] = field(default_factory=list)
    sizes: list[float] = field(default_factory=list)
    upright: bool = True


@dataclass(slots=True)
class ImageGeom:
    """Image XObject geometry only (never decoded)."""

    x0: float
    x1: float
    top: float
    bottom: float


@dataclass(slots=True)
class PageExtractionCandidate:
    """In-memory candidate extraction for one page."""

    page_number: int
    page_width: float
    page_height: float
    page_bbox_x0: float
    page_bbox_top: float
    raw_character_count: int
    characters: list[RawCharCandidate]
    words: list[RawWordCandidate]
    images: list[ImageGeom]
    page_dimension_match: bool
    extraction_error: str | None = None
    strict_duplicate_ratio: float = 0.0
    near_overprint_duplicate_ratio: float = 0.0
    duplicate_layer_count: int = 1
    dominant_duplicate_offset_x: float = 0.0
    dominant_duplicate_offset_y: float = 0.0
    duplicate_layer_coverage_ratio: float = 0.0
    matched_near_duplicate_count: int = 0
    dominant_offset_support_ratio: float = 0.0
    matched_word_span: int = 0
    matched_line_span: int = 0
    top_offset_cluster_support_ratio: float = 0.0
    top_k_offset_cluster_support_ratio: float = 0.0
    offset_cluster_count: int = 0
    duplicate_line_count: int = 0
    duplicate_region_count: int = 0
    page_vertical_span_ratio: float = 0.0
    page_horizontal_span_ratio: float = 0.0
    hard_rule_path: str = "none"
    hard_rule_explanation: tuple[str, ...] = ()
    duplicate_layer_evidence: object | None = None
    near_overprint_composite_evidence: bool = False
    near_overprint_cleaned: bool = False
    near_overprint_ambiguous: bool = False
