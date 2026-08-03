# ADR 0053 — Prototype handwriting-router annotation path

## Status

Accepted (Phase 5 Task A)

## Context

ADRs 0051–0052 established a release-hardening annotation programme: dual
blinded pilot review, page-coverage correction before crop labelling, six-group
held-out caution, and an unauthorised full ~45k primary queue. That tooling
remains valuable, but treating every gate as a prerequisite stalls the Phase 5
purpose: classify detected regions and enforce routing so handwritten and
uncertain regions never reach Paddle recognition.

Phase 5 routing doctrine (unchanged by this ADR):

```text
printed     → existing Paddle printed-text recogniser
handwritten → no Paddle recognition; preserve detector ID/geometry;
              reserved_for_vision / pending_phase_6
uncertain   → same as handwritten
non_text    → no Paddle recognition; suppress from text recognition
```

“Route to vision” means reservation only (`reserved_for_vision`,
`pending_phase_6`). It does **not** mean calling OpenAI or any vision provider
during Phase 5.

## Decision

1. **Single-reviewed project sample is enough to begin prototype model
   development.** A deterministic ~300-crop queue
   (`phase5-prototype-primary-v1`, seed 4101) drawn from the existing 600-crop
   pilot, with active coverage-issue pages excluded from the sample (not deleted
   from the corpus), is the default human labelling path for Task A.
2. **Dual review and adjudication remain useful release-hardening tools** but
   are not prerequisites for the first local writing-style classifier.
3. **The ten outstanding page-coverage correction entries** remain known corpus
   gaps and stay on the private worklist, but they do not block prototype
   training. Crops from those pages are simply omitted from the prototype queue.
4. **Six source groups are insufficient for a strong final release
   generalisation claim**, but they do not block prototype training and
   integration.
5. **The full ~44,951-crop primary queue remains parked** and still requires
   explicit `--authorise-full-queue`.
6. **The current prototype must not claim final production accuracy.** Labels
   exist to train a local style classifier that will later enforce the Paddle
   bypass invariant — not to transcribe handwriting.
7. **Release exit evidence** will still require an agreed routing threshold and
   **zero handwritten/uncertain leakage into Paddle**, plus the automated
   proofs that printed regions reach Paddle while handwritten, uncertain, and
   non_text never do, with detector-owned IDs/geometry preserved and no vision
   provider called in Phase 5.

## Consequences

- Operators label `prototype-primary` with one opaque reviewer ID (single pass).
- `uncertain` crops are retained but excluded from initial three-class model
  fitting; exclusions remain distinct from `uncertain`.
- Release dual-review, coverage correction, and full-queue authorisation tooling
  stay in the repository and remain available for later hardening.
- Training, ONNX export, live OCR wiring, and Phase 6 vision requests are out of
  scope for Task A.

## Related

- ADR 0051 (human label dataset), ADR 0052 (pilot and coverage gate) — not
  superseded for release hardening; this ADR clarifies the prototype path.
- `docs/operations/phase-5-labelling.md`
- `docs/evaluation/phase-5-prototype-labels.md` (after human review)
