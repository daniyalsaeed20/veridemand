# OCR runtime recovery

## Symptoms

| UI | Meaning |
|----|---------|
| Printed OCR is starting + progress | Initialization in progress |
| Printed OCR could not start + Retry OCR | Retryable failure |
| Printed OCR could not start without Retry | Terminal configuration/model issue |
| Printed OCR is disabled | `OCR_ENABLED=false` |
| Backend connection unavailable | Frontend cannot reach the API |

## Retry OCR

1. Open Documents & queue.  
2. Confirm the failure reason and suggested action.  
3. Press **Retry OCR** (enabled only when `retryable=true`).  
4. Watch the progress panel; do not refresh the browser.  
5. Uploaded documents remain in the session.

`POST /api/v1/runtime/ocr/retry` returns **202** and continues initialization in
the background. It does **not** restart the operating-system backend process.

## Check connection

When the backend is unreachable, use **Check connection** (not Retry OCR). Start
or restore the API process, then re-check.

## Manual acceptance (test injection)

Test injection is forbidden when `APP_ENV=production`. Defaults are off.

### Test A — delayed startup

```powershell
$env:UV_PROJECT_ENVIRONMENT = ".venv-ocr"
$env:OCR_TEST_STARTUP_DELAY_SECONDS = "8"
# start API + frontend as usual
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
Check connection (not Retry OCR).

Do not use private documents for these tests.
