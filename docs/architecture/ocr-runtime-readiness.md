# OCR runtime readiness

## Purpose

Printed OCR runs in a supervised subprocess (`OcrWorkerManager`). Cold start can
take tens of seconds. The API remains live while OCR initializes; readiness and
the Documents & queue panel expose a structured status instead of a generic
“starting or unavailable” warning.

## Source of truth

| Surface | Role |
|---------|------|
| `OcrWorkerManager.runtime_status()` | Process-local lifecycle state |
| `GET /health/ready` → `ocr_runtime` | Observational status for UI/operators |
| `POST /api/v1/runtime/ocr/retry` | Operator-initiated re-initialization |
| `GET /health/live` | Process liveness only (never blocked by OCR) |

Health checks never start a model load. Only lifespan startup and the retry
endpoint call the shared `ensure_started` / `retry_initialization` path.

## States

`not_started` · `starting` · `loading_detector` · `loading_recognizer` ·
`warming_up` · `ready` · `failed` · `disabled`

## Startup stages (Step N of 5)

1. Checking OCR configuration  
2. Verifying model files  
3. Loading detector  
4. Loading recognizer  
5. Warming OCR runtime  

Detector and recognizer stages bracket the combined PaddleOCR constructor; the
pipeline still loads as one unit (no accuracy or model changes).

## Error codes

Stable snake_case codes under `OcrRuntimeErrorCode` (for example
`ocr_dll_load_failed`, `ocr_models_missing`). The UI never string-matches free
text. Payloads include `user_message`, `operator_hint`, and a sanitized
`technical_detail` (no secrets, private paths, OCR text, or stack traces).

## Retryability

Retryable examples: transient load/warmup failures, startup timeout, OOM, Windows
DLL/Torch conflict after switching to `.venv-ocr`.

Non-retryable until corrected: OCR disabled, invalid configuration, missing
models, integrity failure, missing Python dependency.

## Windows OCR-only environment

Conflicting Torch + Paddle installs produce DLL load failures. Prefer:

```powershell
pnpm dev:ocr
```

Or backend only:

```powershell
pnpm dev:backend:ocr
```

These set `UV_PROJECT_ENVIRONMENT=.venv-ocr`, sync `--group ocr`, refuse Torch,
and print the Python executable and build identity before uvicorn starts.

Manual equivalent:

```powershell
$env:UV_PROJECT_ENVIRONMENT = ".venv-ocr"
uv sync --group ocr
```

Then Retry OCR from the UI (or restart the API process in that environment).

Plain `pnpm dev` / `pnpm dev:backend` do **not** force `.venv-ocr` and are unsuitable
for Windows printed-OCR work when the default `.venv` also contains Torch.
