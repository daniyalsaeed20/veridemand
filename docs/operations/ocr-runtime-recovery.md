# OCR runtime recovery

## Symptoms

| UI | Meaning |
|----|---------|
| Session active / Offline / Reconnecting | SSE session stream only (not backend liveness) |
| Printed OCR is starting + progress | Initialization in progress (or readiness still checking) |
| Printed OCR could not start + Retry OCR | Retryable failure (in-process) |
| Printed OCR cannot start in this backend process | Mixed/wrong Python env; restart required |
| Printed OCR could not start without Retry | Terminal configuration/model issue |
| Printed OCR is disabled | `OCR_ENABLED=false` |
| Runtime readiness unavailable | Backend live; readiness probe failed |
| Backend connection unavailable | Frontend cannot reach `/health/live` |

## Restart required (mixed environment)

When `restart_required=true` (typically `ocr_dll_load_failed` with Torch/Paddle
conflict or a non-`.venv-ocr` backend):

1. Do **not** press Retry OCR (the endpoint rejects it and does not bump attempts).  
2. Copy `pnpm dev:ocr` from the panel.  
3. Stop the current backend process.  
4. Start with `pnpm dev:ocr` (on Windows, `pnpm dev` routes here too).

In-process retry cannot switch the Python environment.

## Retry OCR

1. Open Documents & queue.  
2. Confirm the failure reason and suggested action.  
3. Press **Retry OCR** (enabled only when `retryable=true` and not restart-required).  
4. Watch the progress panel; do not refresh the browser.  
5. Uploaded documents remain in the session.

`POST /api/v1/runtime/ocr/retry` returns **202** and continues initialization in
the background. It does **not** restart the operating-system backend process.
Restart-required failures return **400** `ocr_retry_not_allowed`.

## Check connection

When the backend is unreachable, use **Check connection** (not Retry OCR). Start
or restore the API with `pnpm dev:ocr` (Windows OCR), then re-check.

## Manual acceptance (test injection)

Test injection is forbidden when `APP_ENV=production`. Defaults are off.
See also [backend-connection-recovery-acceptance.md](../evaluation/backend-connection-recovery-acceptance.md).

### Test A — delayed startup

```powershell
$env:UV_PROJECT_ENVIRONMENT = ".venv-ocr"
$env:OCR_TEST_STARTUP_DELAY_SECONDS = "8"
pnpm dev:ocr
```

Expect stage labels and an indeterminate progress bar, then the warning clears
when ready.

### Test B — retryable failure

```powershell
$env:OCR_TEST_FAIL_ONCE_CODE = "ocr_warmup_failed"
```

Expect the exact reason, then Retry OCR → new attempt → ready without refresh.

### Test C — terminal failure

```powershell
$env:OCR_TEST_FAIL_CODE = "ocr_models_missing"
```

Expect missing-model wording and no enabled Retry OCR.

### Test D — backend unreachable

Stop the API after the UI loads. Expect Backend connection unavailable and
Check connection (not Retry OCR). Session badge becomes Offline (not Session active).

### Test E — ready not ready while live

With live 200 and ready 503 (OCR failed/starting), the UI must **not** show
Backend connection unavailable. Session active remains if SSE is connected.

### Test F — wrong API base / CORS

Point the frontend at a non-VeriDemand origin. Expect Backend connection
unavailable; do not offer Retry OCR as the primary action.

Do not use private documents for these tests.
