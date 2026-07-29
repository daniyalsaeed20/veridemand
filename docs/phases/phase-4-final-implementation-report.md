# Phase 4 final implementation report (consolidation)

Consolidation report template for Phase 4 visual detection and printed OCR after
Corrections 1–7. Gate checkboxes remain **pending verification** until release
evidence is recorded on the consolidation branch.

**Tag target:** `phase-4-visual-detection-printed-ocr-v2`  
**Do not start Phase 5 until this report’s exit gates are PASSED with evidence.**

## Scope

Document-extraction Phase 4 only: canonical PDF → native trust → hybrid routing →
verified embedded OCR → targeted repair → full visual OCR → quality gate →
selected pass → reconciliation → progress/ETA → fair scheduling → cleanup.

Out of scope: handwriting classifier / HTR, vision LLM, final reading order,
final table/form structure, demand-letter product surface.

## Corrections 1–7 summary

| Correction | Theme | Primary refs |
|------------|-------|--------------|
| 1 | Embedded OCR authority invariants; sparse coverage → full OCR | ADR 0032; sparse synthetic fixture |
| 2 | Duplicate-layer Path A/B truthfulness; billing hybrid routing | [correction-2](correction-2-duplicate-layer-billing-routing.md) |
| 3 | Text-rich native salvage; glyph quarantine | [correction-3](correction-3-text-rich-native-routing.md) |
| 4 | Progress events, page indices, clocks, deadlines, ETA | [progress](../architecture/phase-4-progress-events.md), ADRs 0029–0033 |
| 5 | Dense-form quality evidence; primary/fallback selection | [quality gate](../architecture/phase-4-ocr-quality-gate.md), ADRs 0034–0037 |
| 6 | Targeted regional repair + fallback | [repair](../architecture/phase-4-targeted-region-repair.md), ADRs 0038–0041 |
| 7 | Page-boundary fair scheduling | [fair scheduling](../architecture/phase-4-fair-scheduling.md), ADRs 0042–0046 |

Pipeline overview: [phase-4-overview.md](../architecture/phase-4-overview.md).

## Consolidation audit summary

| Item | Status |
|------|--------|
| `FailedRegion` removed | Done (no remaining type in backend) |
| LEGACY progress constants removed | Done (progress weights via `progress_weights` / `progress_model`) |
| `FAIR_OCR_PAGE_CHUNK_SIZE` migrator kept | Done (maps to `FAIR_OCR_PAGE_QUANTUM` with deprecation warning) |
| Cursor rule updated | Done (Phase 4 complete; do not start Phase 5 until exit gates green) |
| `DEPENDENCY_INVENTORY.md` pointer added | Done (points at `docs/dependencies/` including security-review) |
| Port / build-identity isolation | Done (`scripts/lib/api_process_guard.py`; smoke `--require-build-identity` default) |
| OCR Settings default | `PP-OCRv5_mobile_*` (ADR 0023); calibration docs may cite PP-OCRv6 medium (ADR 0018) |
| `OCR_WORKERS` | Default 1 |
| Progress cap | 65% |

## Port isolation

Acceptance and smoke runners resolve the API base against `/health/live`
`git_commit` vs repository HEAD. Matching builds may be reused. Mismatched or
unknown listeners fail the gate with a diagnostic. **Unrelated processes are
never killed.** Operators stop the correct PID only. See
[phase-4-local-runtime.md](../operations/phase-4-local-runtime.md) and
[phase-4-troubleshooting.md](../operations/phase-4-troubleshooting.md).

## Documentation delivered with this consolidation

- [phase-4-overview.md](../architecture/phase-4-overview.md)
- [phase-4-local-runtime.md](../operations/phase-4-local-runtime.md)
- [phase-4-troubleshooting.md](../operations/phase-4-troubleshooting.md)
- [phase-4-security-review.md](../security/phase-4-security-review.md)
- [security-review.md](../dependencies/security-review.md)
- [phase-4-final-baseline.md](../evaluation/phase-4-final-baseline.md)

## Exit gate checklist (Phase 4 release)

Mark each item only after evidence is attached (CI SHA, smoke log path, opaque
acceptance JSON under gitignored `tmp/`, or equivalent). Until then leave
unchecked.

### Architecture

- [ ] Pipeline matches overview order (canonical → trust → quarantine → hybrid →
      embedded → repair → full OCR → quality gate → selected pass →
      reconciliation → progress → fair scheduling → cleanup)
- [ ] ADRs 0017–0046 consistent with code; conflicts reported, not silently
      reinterpreted
- [ ] Phase 5 modules (HTR / vision LLM / final structure) absent from runtime path

### Quality

- [ ] Synthetic printed OCR eval recorded (or waiver with rationale)
- [ ] Dense-form quality gate behaviour evidenced (Correction 5)
- [ ] Targeted repair eligibility / fallback evidenced (Correction 6)
- [ ] Opaque private route histograms recorded without transcripts

### Performance

- [ ] `OCR_WORKERS=1` baseline timings filled in final baseline doc
- [ ] 104-page (or equivalent large) document bounded-memory / wall time recorded
- [ ] Fair scheduling batch metrics recorded (Correction 7)

### Progress

- [ ] Overall progress never exceeds 65% and never decreases
- [ ] Heartbeats do not advance overall percent
- [ ] Document vs selected page indices correct in SSE and UI
- [ ] Operation-attempt lifecycle invariants hold (one terminal per attempt)

### Reliability

- [ ] `/health/ready` green with models bootstrapped
- [ ] Worker restart / generation behaviour acceptable on acceptance machine
- [ ] Cancellation and session cleanup leave no residual session trees
- [ ] Build-identity isolation prevents gates against obsolete APIs

### Security

- [ ] Upload validation / macro rejection still enforced
- [ ] Logs free of document text in sampled acceptance runs
- [ ] `include_verification_candidates` defaults false
- [ ] Test injection flags off for release evidence
- [ ] Dependency scans triaged per [security-review.md](../dependencies/security-review.md)
- [ ] No regulatory compliance claim asserted

### Quality gates (automation)

- [ ] `pnpm check` green on consolidation SHA
- [ ] `pnpm contracts:check` green
- [ ] `pnpm smoke:corpus:critical` green against matching build identity
- [ ] `pnpm smoke:corpus:phase4` green with OCR enabled and models present
- [ ] Unit / e2e suites required by CI green

### Boundary

- [ ] Handwriting assessment remains `pending_phase_5`
- [ ] No local HTR / ONNX handwriting classifier / OpenAI vision in path
- [ ] No final table/form structure claims
- [ ] Tag `phase-4-visual-detection-printed-ocr-v2` created only after PASSED

## Evidence pointers (fill on consolidation)

| Gate area | Evidence location | Status |
|-----------|-------------------|--------|
| Architecture | Pending verification | Pending |
| Quality | `docs/evaluation/phase-4-final-baseline.md` | Pending |
| Performance | same | Pending |
| Progress | CI + lifecycle tests | Pending |
| Reliability | readiness + residual-session check | Pending |
| Security | `docs/security/` + `docs/dependencies/security-review.md` | Pending |
| Quality gates | CI logs on consolidation SHA | Pending |
| Boundary | code search / dependency inventory | Pending |

## Release decision

| Field | Value |
|-------|-------|
| Consolidation SHA | Pending verification |
| Annotated tag | `phase-4-visual-detection-printed-ocr-v2` (create only when PASSED) |
| Phase 5 start | **Blocked** until this report is PASSED |

When all checklist boxes are checked with evidence, record **PHASE 4 PASSED**
here and only then begin Phase 5 planning.
