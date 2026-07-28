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

## Deprecations

- Field `NativeTrustComponents.duplication_score` renamed to
  `duplication_quality_score`. Regenerate contracts; no silent dual meaning.
