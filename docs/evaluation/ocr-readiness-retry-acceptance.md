# OCR readiness / retry acceptance

## Scope

Pre-Phase 6 hotfix for structured OCR readiness, progress, and operator retry.
Does not change OCR accuracy, handwriting reservation, or Phase 6.

## Automated coverage

| Layer | Evidence |
|-------|----------|
| Backend unit/API | `backend/tests/test_ocr_runtime_readiness.py` |
| Frontend unit | `frontend/src/features/health/OcrReadinessPanel.test.tsx` |
| E2E | `frontend/e2e/ocr-readiness-retry.spec.ts` |

## Acceptance checklist

- [x] Restart-required DLL/env failure shows `pnpm dev:ocr` and hides Retry OCR
- [x] `POST /runtime/ocr/retry` rejects restart-required without bumping attempt_number
- [x] Starting state shows stage label, Step N of 5, elapsed time, indeterminate progress
- [x] Retry hidden while starting
- [x] Retryable failure shows `user_message` + `operator_hint` + Retry OCR
- [x] Non-retryable failure disables Retry with helper text
- [x] Technical details + Copy diagnostics are sanitized
- [x] Successful retry reaches ready without browser refresh
- [x] Backend unreachable shows Check connection
- [x] Process controls stay disabled until OCR ready; uploads preserved
- [x] No generic “starting or unavailable” copy remains
- [x] `/health/live` stays 200 during OCR failure
- [x] `/health/ready` stays observational (does not load models)
- [x] Phase 5 page reservation and feature defaults unchanged

## Manual Tests A–D

See [ocr-runtime-recovery.md](../operations/ocr-runtime-recovery.md).
