# Phase 5 handwriting seed readiness

**Status:** PROJECT HANDWRITING SEED READY

Aggregate / opaque only. No private IDs, page references, filenames, paths,
reviewer IDs, hashes, or visible text.

## Candidate pages

1. Candidate pages offered: **125**
2. Candidate pages inspected: **125**
3. Pages containing usable handwriting: **9**
4. Human-confirmed handwritten regions: **55**
5. Canonical regions after exact deduplication: **55**
6. Source groups represented: **3**
7. Broad source families represented (privacy-safe):

- `image_document`: **6**
- `medical_form`: **41**
- `police_form`: **8**

- Suppressed small family buckets (seed count):
  **0**

8. Handwritten region categories (structured tags only):

- `cursive`: **22**
- `digits`: **10**
- `hand_printed`: **10**
- `longer_note`: **2**
- `signature`: **11**

9. Excluded (no usable handwriting): **107**
10. Deferred: **0**
11. Pages marked complete after seed collection: **19**
12. Exact duplicate count: **0**
13. Perceptual duplicate warnings: **3**

### Queue composition (aggregate)

- Uncertain-source pages included: **43**
- Coverage-worklist pages included: **10**
- Target region count: **100**

## Known limitations

- Private crops originate from combined Paddle detection/recognition evidence.
- Empty-text detections were dropped from the original corpus.
- Handwriting Paddle failed to detect may still be underrepresented until seeds
  are added.
- Signatures and handwritten form values were historically underrepresented.
- The 54 prototype `uncertain` labels were not automatically reinterpreted.
- Seed collection is human-only; no dual review, adjudication, or held-out
  freeze in Task A2.

## Readiness

- Project seed sufficient to attempt prototype model development:
  **yes**
- External handwriting supplementation recommended:
  **yes**

## Policy

- Report version: `phase5-handwriting-seed-report-v1`
- Seed schema: `phase5-handwriting-seed-v1`
- Source type: `human_confirmed_handwriting_seed`
- No OCR, classifier, vision provider, or transcription in Task A2.
- Existing prototype review events were not mutated.

See `docs/operations/phase-5-labelling.md` and ADR 0053 / Task A2.
