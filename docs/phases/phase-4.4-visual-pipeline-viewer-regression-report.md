# Phase 4.4 — Visual pipeline and canonical viewer regression

## Starting branch and commit

- Starting branch: `fix/phase-4-adaptive-image-ocr-performance`
- Starting HEAD: `4d63df465bce4e085236b7b84ee5b0410e4f06ab` (`phase-4-visual-detection-printed-ocr-v1.4`)
- Corrective branch: `fix/phase-4-visual-pipeline-viewer-regression`
- Starting acceptance commit: `21c5b7bdef0df3ac10a1d9a33767c7a457d95cdf`
- Throughput WIP stashed as `wip-phase44-throughput` (not applied)

## Regression root cause (automated fix)

| Item | Detail |
|------|--------|
| First bad state | Uncommitted fair-scheduler WIP after page selection |
| Exception | `TypeError: unexpected keyword argument 'document_pages_total'` |
| Location | `EventBroker.publish` / coordinator post-selection publish |
| Why all docs failed | Every Phase 4 document hit the same publish before OCR |
| Why CI missed it | No test published those selection kwargs through the broker |

## Private subset acceptance (opaque labels only)

Privacy: `fixtures/private/private_*.pdf` are gitignored; not tracked; not copied under docs.

| Label | Pages | Terminal status | Visual status | Selected / completed / failed | Native retained | Policy | Canonical meta/full/range/416 | SHA stable | Duration | Result |
|-------|------:|-----------------|---------------|------------------------------:|----------------:|--------|-------------------------------|------------|---------:|--------|
| private_scan_001 | 2 | visual_processing_complete | visual_processing_complete | 2 / 2 / 0 | 0 | visual_authority | 200 / 200 / 206 / 416 | yes | 53.8s | pass |
| private_digital_001 | 1 | visual_processing_complete | not_required | 0 / 0 / 0 | 1 | native_authority | 200 / 200 / 206 / 416 | yes | 1.5s | pass |
| private_mixed_001 | 2 | visual_processing_complete | visual_processing_complete | 1 / 1 / 0 | 1 | mixed_authority | 200 / 200 / 206 / 416 | yes | 20.6s | pass |

Worker generation observed: 1 (scan/mixed). Visual summary HTTP status: 200 for all three.

### Intentional visual-failure (synthetic)

| Label | Status | Visual summary | Native summary | Canonical | Failure code | Result |
|-------|--------|----------------|----------------|-----------|--------------|--------|
| synthetic_inject | visual_processing_failed | 200 | 200 | 200 + viewable | ocr_runtime_unavailable | pass |

Inject setting: `OCR_INJECT_VISUAL_FAILURE` (test/acceptance only; default false).

### PDF.js viewer

Playwright private viewer acceptance: **passed** (nonblank `data-render-status=rendered`, page nav, zoom, fit width, rotate, A→B→A switching). WASM `/pdfjs-wasm/jbig2.wasm` → 200 `application/wasm`.

### Concurrent processing and viewing

Open-canonical available for all three after terminal; viewer switching verified while stack remained live.

## Local evidence

Gitignored aggregates: `tmp/phase44-acceptance/acceptance.local.json` (opaque labels only; no private filenames/text).

## Final verification (local)

- `pnpm models:ocr:verify` / `pnpm test:ocr` / `pnpm smoke:corpus:phase4`: pass
- `pnpm check` components through OCR integration: pass
- `pnpm -C frontend test:e2e` with `OCR_ENABLED=false`: 15 passed
- Private-corpus tracking guard: pass
- Residual sessions: none
- Stash `wip-phase44-throughput`: present, not applied

## Phase boundary

- Fair scheduler / throughput WIP not applied.
- Phase 5 not started.
- Tag `phase-4-visual-detection-printed-ocr-v1.5` created only after final CI on the delivery commit.
