# Phase 4 — Targeted region repair (Correction 6)

## Purpose

When embedded OCR is mostly trustworthy but a small number of spatially bounded
regions fail verification, VeriDemand repairs only those regions instead of
running full-page visual OCR.

## Module map

| Concern | Location |
|---------|----------|
| Eligibility evidence | `backend/app/contracts/repair.py`, `repair_eligibility.py` |
| Clustering | `repair_clustering.py` |
| Methods | `repair_methods.py` + `PaddleOcrAdapter.recognise_only` / `detect_and_recognise_crop` |
| Coordinates | `repair_coordinates.py` |
| Reconciliation | `repair_reconcile.py` |
| Quality gate | `repair_quality.py` |
| Pipeline / publish | `repair_pipeline.py` |
| Service wiring | `VisualOcrService` targeted-repair branch |

## Policy version

`phase4-targeted-repair-v1`

Central thresholds live in settings → `RoutingPolicy` (fail ratio, region count,
coverage, largest-region coverage, retained coverage of candidates, visual
floor, quality gate knobs).

## Methods

1. **recognition_only** — trusted geometry; crop known boxes; bypass detection.
2. **local_detection_and_recognition** — detect+recognise inside the padded crop only.

At most one bounded repair attempt per page. One tested transition from
recognition-only → local detection is allowed when the first attempt yields no
usable words. Otherwise fall back to full visual OCR (Correction 5 quality gate).

## Provenance

Public words identify:

- `native_pdf_word`
- `verified_embedded_ocr_word`
- `targeted_repair_recognition_word`
- `targeted_repair_local_ocr_word`
- `printed_visual_ocr_word`

Normal UI source label: **Verified embedded OCR with visual repair**.

## Publication and cleanup

Repair writes to staging, validates, then publishes atomically. Crops are
runtime-only under `staging/targeted_repair/` and are removed on success,
failure, cancellation, session reset, and shutdown. Never logged as text or
images.

## Phase 5 boundary

Handwriting assessment remains `pending_phase_5`. No local HTR, no handwriting
classifier productization, no vision LLM.
