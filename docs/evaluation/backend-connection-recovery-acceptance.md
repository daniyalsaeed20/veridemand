# Backend connection recovery acceptance

Acceptance evidence for separating backend **liveness**, **session SSE**, **readiness**,
and **OCR runtime** status after the post–Phase 5 connection/OCR recovery hotfix.

## Root causes addressed

| ID | Category | Cause |
|----|----------|-------|
| A | `FRONTEND_STATUS_CLASSIFICATION_BUG` | Green **Live** was SSE session connectivity; **Backend connection unavailable** was any readiness query error (timeout, HTTP 500), not `/health/live` failure |
| B | `WRONG_PYTHON_ENVIRONMENT` / `TORCH_PADDLE_DLL_CONFLICT` | `pnpm dev` used default `.venv` (Torch+Paddle); Windows `shm.dll` failed OCR worker and in-process `paddleocr` import on `/health/ready` |

## Operator launch (Windows OCR)

```powershell
pnpm dev:ocr
# or backend only:
pnpm dev:backend:ocr
```

These force `UV_PROJECT_ENVIRONMENT=.venv-ocr`, sync the OCR group, refuse Torch,
print `sys.executable` / git identity / URLs, then start uvicorn + frontend.

Non-OCR local work may still use `pnpm dev` / `pnpm dev:backend`. Model-dev Torch
stays in `.venv-model-dev`.

## UI classification rules

| Signal | Meaning |
|--------|---------|
| Session active / Offline / Reconnecting | SSE event stream only |
| Backend connection unavailable | `/health/live` transport failure only |
| Runtime readiness unavailable | Live OK; readiness HTTP/body failure (not timeout) |
| Printed OCR is starting | OCR stages **or** readiness client timeout while live |
| OCR failed (+ Retry OCR when retryable) | Structured `ocr_runtime` failed |
| Process enabled | Live OK, ready 200, `ocr_runtime.ready` |

## Controlled tests A–F

Injection defaults off; forbidden when `APP_ENV=production`.

| Test | Setup | Expect |
|------|-------|--------|
| A delayed start | `OCR_TEST_STARTUP_DELAY_SECONDS=8` via `pnpm dev:ocr` | Starting UI; then ready; Process enabled |
| B retryable | `OCR_TEST_FAIL_ONCE_CODE=ocr_warmup_failed` | Retry OCR → ready; session preserved |
| C terminal | `OCR_TEST_FAIL_CODE=ocr_models_missing` | No Retry; terminal copy |
| D backend stop | Stop API after UI load | Backend connection unavailable + Check connection; badge Offline (not Session active) |
| E ready 503 + live 200 | OCR failed / not ready | No “Backend connection unavailable”; Session active if SSE up |
| F wrong URL / CORS | Bad `VITE_API_BASE_URL` | Unreachable; not OCR Retry |

## Gate evidence (fill at verification)

| Check | Result |
|-------|--------|
| Torch absent in `.venv-ocr` | PASS |
| Paddle import OK | PASS |
| `pnpm models:ocr:verify` | PASS |
| Critical smoke feature-off (`:8020`) | PASS |
| Phase 4 smoke feature-off (`:8020`) | PASS |
| Page reservation acceptance feature-on | PASS (215/107; 9/9; 55/55) |
| Full Playwright e2e | PASS (27 passed, 5 skipped) |
| `GET /health/live` 200 | PASS (`pnpm dev:ocr`, git at verify time) |
| `GET /health/ready` → OCR ready | PASS (~1s after warm worker) |
| Browser: no backend-unavailable while Session active | PASS |
| Browser: Session active label (not backend “Live”) | PASS |
| Process enabled when OCR ready | PASS (Process not OCR-blocked; empty queue stays disabled) |
| Test D stop API after load | PASS — Reconnecting + Backend connection unavailable + Check connection; no Retry OCR |
| Test E live 200 + ready OCR | PASS — Session active, no unreachable |
