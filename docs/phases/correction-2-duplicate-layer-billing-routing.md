# Correction 2 — Duplicate-layer truthfulness and billing routing

**Branch:** `fix/phase-4-billing-duplicate-routing`  
**Policy version:** `phase3-v1.6`

## Summary

- Canonical `DuplicateLayerEvidence` is the single source of truth for Path A/B.
- Path B requires coherent line/region structure; sparse character matches cannot
  select Path B.
- `duplication_quality_score` replaces `duplication_score` (higher = less
  duplication pressure).
- Phase 3 document escalation remains provisional; Phase 4 recovers individually
  trusted suppressed pages to digital-native / embedded routes.
- Routing-only audit: `scripts/audit_billing_routing_only.py` (opaque labels only).
- Full private acceptance: `scripts/accept_correction2_private_billing.py`
  (opaque label `private_billing_document`).

## Private nine-page acceptance (sanitised)

- Opaque label: `private_billing_document`
- Page count: 9
- Final routes: digital_native ×7, full_visual_ocr ×2
- Duplicate paths: none ×7, A ×1, B ×1
- Final document policy: `mixed_authority`
- Evidence consistent: true
- Overlays: OCR pages have visual boxes; native pages use native authority

## Deprecations

- Field `NativeTrustComponents.duplication_score` renamed to
  `duplication_quality_score`. Regenerate contracts; no silent dual meaning.
