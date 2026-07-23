# Phase 4 implementation report — Visual detection and printed OCR

## Status

**PHASE 4 PASSED — READY FOR PHASE 5**

Remote CI on the Phase 4 branch is green (lint/test, Phase 4 smoke with real OCR,
Playwright e2e with `OCR_ENABLED=false`). Annotated tag
`phase-4-visual-detection-printed-ocr-v1` tracks the delivery commit on
`phase/4-visual-detection-printed-ocr`.

Local evidence: ruff/mypy clean; backend/frontend unit suites green; frontend build OK;
OCR runtime verify OK; synthetic OCR eval pass (clean mean CER ~0.009);
ADRs 0017–0021 and architecture docs on the Phase 4 branch.

## Baseline

| Item | Value |
|------|-------|
| Branched from | `phase-3-native-extraction-trust-gate-v1.7` (`0cbc475`) |
| Progress cap | 65% |
| OCR stack | paddleocr 3.7.0 + paddlepaddle 3.3.0 CPU |
| Models | PP-OCRv6_medium_det / PP-OCRv6_medium_rec |
| Render DPI | 200 (SoT placeholder 300 / PP-OCRv5 not rewritten — ADR 0018) |

## Delivered

- `backend/app/extraction/visual/*` — render, visibility, Paddle adapter, layout,
  long-lived worker + manager, service, atomic publish.
- Contracts: `visual.py`, `ocr.py`; document/progress/error extensions; OpenAPI/Zod.
- Coordinator runs visual after native; lifespan manages OCR worker when enabled.
- APIs: `/visual/summary`, `/visual/pages/{n}`; health checks for pypdfium2 / paddle.
- Frontend: `features/visual/*` panels, overlays, lazy page fetch.
- Scripts: model bootstrap/verify, printed OCR eval, private opaque eval, Phase 4 smoke subset.
- Docs: architecture, ADRs 0017–0021, dependency/licence inventories, smoke README.

## Exit evidence

1. `pnpm check` (OCR verify + integration when `.models/paddleocr/model-record.json` exists).
2. `pnpm smoke:corpus:phase4` with `OCR_ENABLED=true` and models present (CI smoke job).
3. `pnpm evaluate:ocr` baseline under `docs/evaluation/`.
4. CI: lint/test + real CPU OCR + Phase 4 smoke; Playwright e2e OCR-off for Phase 2/3 UX.
5. Annotated tag `phase-4-visual-detection-printed-ocr-v1` on the Phase 4 branch (not `main`).

## Explicit non-goals (Phase 5+)

Handwriting classifier, ONNX, OpenAI vision, PP-Structure, final reading order,
tables, export, `final_result_available=true`.
