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

- [ ] Restart-required DLL/env failure shows `pnpm dev:ocr` and hides Retry OCR
- [ ] `POST /runtime/ocr/retry` rejects restart-required without bumping attempt_number
- [ ] Starting state shows stage label, Step N of 5, elapsed time, indeterminate progress
- [ ] Retry hidden while starting
- [ ] Retryable failure shows `user_message` + `operator_hint` + Retry OCR
- [ ] Non-retryable failure disables Retry with helper text
- [ ] Technical details + Copy diagnostics are sanitized
- [ ] Successful retry reaches ready without browser refresh
- [ ] Backend unreachable shows Check connection
- [ ] Process controls stay disabled until OCR ready; uploads preserved
- [ ] No generic “starting or unavailable” copy remains
- [ ] `/health/live` stays 200 during OCR failure
- [ ] `/health/ready` stays observational (does not load models)
- [ ] Phase 5 page reservation and feature defaults unchanged

## Manual Tests A–D

See [ocr-runtime-recovery.md](../operations/ocr-runtime-recovery.md).
