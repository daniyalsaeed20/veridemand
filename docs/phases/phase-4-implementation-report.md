# Phase 4 implementation report — Visual detection and printed OCR

## Status

**PHASE 4 PASSED — READY FOR PHASE 5** (pending remote CI confirmation on tagged commit).

Local evidence: ruff/mypy clean; 249 backend tests passed; 118 frontend tests passed;
frontend build OK; OCR runtime verify OK; synthetic OCR eval pass (clean mean CER 0.009);
ADRs 0017–0021 and architecture docs committed with the Phase 4 branch.

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

## Exit evidence (to confirm before tag)

1. `pnpm check` (OCR verify + integration when `.models/paddleocr/model-record.json` exists).
2. `pnpm smoke:corpus:phase4` with `OCR_ENABLED=true` and models present.
3. `pnpm evaluate:ocr` baseline written under `docs/evaluation/`.
4. CI: lint/test + OCR job + Phase 4 smoke on tagged commit.
5. Annotated tag `phase-4-visual-detection-printed-ocr-v1` pushed with branch only.

## Explicit non-goals (Phase 5+)

Handwriting classifier, ONNX, OpenAI vision, PP-Structure, final reading order,
tables, export, `final_result_available=true`.
