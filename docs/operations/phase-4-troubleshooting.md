# Phase 4 troubleshooting

Common local failures for Phase 4 visual detection and printed OCR. Remediation
steps never kill unrelated processes. Never paste private document text into
tickets or logs.

## Port conflict / build identity mismatch

**Symptoms**

- Smoke or acceptance exits with `build_identity_mismatch` or `api_port_conflict`
- `/health/live` `git_commit` does not match `git rev-parse HEAD`
- Gates talk to an obsolete or foreign listener on `:8000`

**Remediation**

1. `Invoke-RestMethod http://127.0.0.1:8000/health/live` (or your
   `VERIDEMAND_API_BASE`) and record `git_commit` / `process_id`.
2. If reachable VeriDemand with a mismatched commit: stop **that** PID only
   (Ctrl+C in its terminal), then start `pnpm dev:backend` from current HEAD.
3. If the port is occupied by a non-VeriDemand process: identify the owner
   manually; do not auto-kill. Either free the port or run the API on a free
   port and point smoke/acceptance at that base URL.
4. Re-run with `--require-build-identity` (default on). Do not disable identity
   checks to “make the gate pass.”

Helpers: `scripts/lib/api_process_guard.py`. See
[phase-4-local-runtime.md](phase-4-local-runtime.md) and
[smoke README](../smoke/README.md).

## OCR model missing

**Symptoms**

- `/health/ready` not ready while `OCR_ENABLED=true`
- Bootstrap/verify errors about missing det/rec trees or `model-record.json`

**Remediation**

```bash
uv sync --group ocr
pnpm models:ocr:bootstrap
pnpm models:ocr:verify
```

Confirm Settings model names (`PP-OCRv5_mobile_det` / `PP-OCRv5_mobile_rec` by
default) match directories under `.models/paddleocr/`. Processing must not
download models. If switching to PP-OCRv6 medium for a benchmark, bootstrap
those models explicitly and update settings before readiness checks.

## LibreOffice not found / Word conversion failure

**Symptoms**

- Readiness or DOC/DOCX canonicalisation fails
- Errors referencing `soffice` / LibreOffice

**Remediation**

1. Install LibreOffice Writer.
2. Ensure `soffice` / `soffice.com` is on `PATH`, or set
   `LIBREOFFICE_EXECUTABLE`.
3. Confirm headless conversion can run with an isolated user profile (ADR 0009).
4. Re-check macros are rejected at upload; conversion re-runs Word safety checks.

## PDF.js WASM / blank pages

**Symptoms**

- Viewer shows blank pages on large PDFs
- WASM asset verification fails in `pnpm check`

**Remediation**

```bash
pnpm check:wasm
# or:
uv run python scripts/verify_pdfjs_wasm.py --sync --clean
```

Ensure CORS exposes `Accept-Ranges`, `Content-Range`, `Content-Length`, and
`Content-Type` for the frontend origin (see `backend/app/main.py`). Range
loading must stay enabled for the canonical PDF route.

## Readiness failures (broader)

**Checks**

1. API process alive and identity matches HEAD.
2. OCR models verified when OCR enabled.
3. LibreOffice resolvable if Word uploads are in scope.
4. Temp root writable (`TEMP_ROOT`, default `./temp`).
5. No stuck worker after a prior crash — restart the matching API process;
   confirm a single worker generation after restart.

`/health/ready` ≠ multipage progress proof. Use smoke subsets and acceptance
scripts for behavioural evidence.

## Scheduler / fair OCR issues

**Symptoms**

- Small documents appear stuck behind a large OCR document when fair mode
  should be on
- Unexpected FIFO behaviour
- Warnings about deprecated `FAIR_OCR_PAGE_CHUNK_SIZE`

**Remediation**

1. Confirm `FAIR_OCR_SCHEDULING_ENABLED` (default `true`). Set `false` only
   when intentionally testing Correction 6 FIFO.
2. Prefer `FAIR_OCR_PAGE_QUANTUM` (default 2). The migrator still accepts
   deprecated `FAIR_OCR_PAGE_CHUNK_SIZE` with a warning.
3. Confirm `OCR_WORKERS=1` (or 2) and that the worker did not restart
   unexpectedly (`worker_generation` on `/health/live`).
4. Cancellation should remove ready units cleanly and abort running pages at
   safe checkpoints only (ADRs 0042–0046).

See [phase-4-fair-scheduling.md](../architecture/phase-4-fair-scheduling.md).

## Residual sessions / temp trees

**Symptoms**

- `check_no_residual_sessions.py` fails after `pnpm check`
- Leftover `temp/` session or LibreOffice profile directories

**Remediation**

1. Stop the API cleanly so shutdown cleanup runs.
2. Delete expired sessions via product APIs if still live.
3. Re-run `uv run python scripts/check_no_residual_sessions.py`.
4. Do not commit anything under `temp/` or `fixtures/private/`.

## Progress / index confusion

**Symptoms**

- UI shows impossible labels (e.g. page 20 of 2)
- Overall percent exceeds 65 or decreases

**Remediation**

Use `document_page_number` with `document_pages_total`, and
`selected_page_index` with `selected_pages_total` (or visual variants). Do not
pair legacy `page_number` with legacy `pages_total`. Heartbeats must not advance
overall percent. See
[phase-4-progress-events.md](../architecture/phase-4-progress-events.md).

## Smoke corpus failures

**Remediation**

1. `pnpm smoke:corpus:validate` for checksum / structure issues.
2. Ensure a single matching API (`--require-build-identity`).
3. For Phase 4 visual cases: models present, `OCR_ENABLED=true`.
4. Classify failures as generator, manifest, genuine regression, future-phase,
   or document-scoped exclusion — never weaken production trust thresholds to
   pass one synthetic page.

## Further reading

- [phase-4-local-runtime.md](phase-4-local-runtime.md)
- [phase-4-overview.md](../architecture/phase-4-overview.md)
- [phase-4-security-review.md](../security/phase-4-security-review.md)
