# Correction 3 — Text-rich native routing and glyph quarantine

**Branch:** `fix/phase-4-text-rich-native-routing`  
**Native trust policy version:** `phase3-v1.7`  
**Glyph quarantine policy version:** `phase4-c3-v1`

## Summary

- Isolated unsupported glyphs (private-use checkbox stand-ins, symbol-font
  marks) are quarantined without rejecting an otherwise coherent page.
- Widespread Unicode corruption and material identifier corruption remain
  hard-rejected with distinct reason codes.
- Public route stays `digital_native` with safe warnings such as
  `isolated_glyphs_quarantined` (no new public PageRoute enum value).
- Phase 3 document escalation remains provisional; Phase 4 restores pages on
  their own evidence only.

## Exact 97-page universal-rejection cause (measured)

Opaque label: `private_text_rich_097`

Before Correction 3 salvage (on Correction 2 tip behaviour):

| Metric | Value |
|---|---|
| Proposed digital_native | 42 (restored after escalation) |
| Proposed full_visual_ocr | 55 |
| Dominant failed rule | `high_private_use_character_ratio` |
| Co-occurring | `high_unprintable_character_ratio` (same private-use glyphs) |
| Absolute private-use counts on failed pages | 1–34 (median 13) |
| checkbox_like count | equal to private_use count |

**File / class / method:** `backend/app/extraction/native/trust_policy.py` →
`decide_page_trust` hard ratio checks against
`NativeTrustPolicyConfig.native_max_private_use_ratio` (0.005) under policy
`phase3-v1.6`.

**Cause class:** isolated checkbox / form-mark private-use glyphs (corruption
class D), not widespread ToUnicode failure. Page-level hard reject with no
glyph quarantine forced full OCR on those pages; document escalation then
suppressed clean siblings (later restored by Correction 2).

After Correction 3:

| Metric | Value |
|---|---|
| digital_native | 97 |
| full_visual_ocr | 0 |
| phase3 provisional policy | `native_authority` |

## Page-level salvage policy

- Quarantine invalid glyphs when materiality is `non_material`.
- Retain neighbouring valid words; never publish quarantined strings.
- Material numeric/date token corruption → targeted repair / full OCR path.
- Widespread corruption → hard reject with
  `widespread_unicode_corruption` or `replacement_character_corruption`.

## Routing-only audit

`scripts/audit_private_routing_only.py --label private_text_rich_097`

Billing wrapper remains `scripts/audit_billing_routing_only.py`.

## Full HTTP runtime acceptance (sanitised)

Opaque label: `private_text_rich_097` · 97 pages

Script: `scripts/accept_correction3_private_text_rich.py` against `pnpm dev`
(`/health/ready`, `/api/v1`, upload field `files`).

| Metric | Routing-only | Full HTTP |
|---|---|---|
| digital_native | 97 | 97 |
| full_visual_ocr | 0 | 0 |
| embedded / repair / failed / no_text | 0 | 0 |
| Duration | ~74 s | ~132 s (incl. upload + publish) |
| Final document policy | — | `native_authority` |
| Native pages retained | — | 97 |
| Full OCR selected / completed | — | 0 / 0 |
| Public words (aggregate) | — | 26473 |
| Empty digital_native pages | — | 0 |
| Quarantined glyphs (aggregate) | — | 733 |
| Quarantined regions | — | 733 |
| Pages with glyph warnings | — | 56 (all `non_material`) |
| Material glyph pages | — | 0 |
| Privacy findings (public JSON) | — | 0 |
| `verification_words` leaks | — | 0 |

Viewer (same live session): sampled pages 1, 2, 10, 11, 18, 25, 49, 50, 75, 96, 97 —
nonblank render, `digital_native` / Native PDF text labels, native word overlays,
zoom/fit/rotate, no Printed visual OCR label, no private-use sentinels in DOM,
document card `Native pages retained: 97` / `Full OCR required: 0`.

Billing non-regression (routing-only): `digital_native ×7` / `full_visual_ocr ×2`.

## Privacy

Private PDF stays under gitignored `fixtures/private/`. Committed docs and
reports use only the opaque label and aggregate metrics.
