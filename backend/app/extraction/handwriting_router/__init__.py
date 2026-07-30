"""Phase 5 handwriting style classifier (routing foundation).

Classifies visual region crops as printed / handwritten / non_text and derives
public ``uncertain`` by deterministic abstention. Style classification only —
no local HTR, no geometry invention, no vision LLM.

Task 2 provides the runtime foundation but does **not** wire into Phase 4 OCR.
"""

from __future__ import annotations

from backend.app.extraction.handwriting_router.routing import (
    RoutingThresholds,
    decide_routing_outcome,
)
from backend.app.extraction.handwriting_router.service import (
    HandwritingClassifierService,
    InternalClassificationResult,
)
from backend.app.extraction.handwriting_router.verifier import (
    PackageVerificationResult,
    verify_classifier_package,
)

__all__ = [
    "HandwritingClassifierService",
    "InternalClassificationResult",
    "PackageVerificationResult",
    "RoutingThresholds",
    "decide_routing_outcome",
    "verify_classifier_package",
]
