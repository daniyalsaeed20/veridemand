# ADR 0009 - LibreOffice conversion

- Status: Accepted
- Date: 2026-07-22
- Phase: 2

## Context

Phase 2 must canonicalise legacy `.doc` and `.docx` uploads without embedding a
Word engine in Python. Upload-time macro/archive checks already reject unsafe
packages.

## Decision

- Use **LibreOffice headless** (`soffice` / `soffice.com`) as an **external
  runtime**, not a Python package.
- Discovery order: configured `LIBREOFFICE_EXECUTABLE`, then `PATH`, then known
  Windows install paths.
- Each conversion runs in an isolated per-job staging tree:
  `staging/libreoffice/<job_id>/{profile,out}` with `-env:UserInstallation=…`
  pointing at the job profile directory.
- Subprocess invocation uses `shell=False`, bounded timeout, and controlled
  `TMP`/`HOME`/`USERPROFILE` under the job profile.
- Before conversion, upload-time Word safety checks are **re-run** (macros,
  archive policy).
- Readiness requires a resolvable LibreOffice executable; CI installs
  `libreoffice-writer`.

## Consequences

- Conversion fidelity and fonts depend on the host LibreOffice build (version
  stored on the document).
- Operators must install LibreOffice locally; Python dependencies alone are
  insufficient for Word canonicalisation.
- Staging/profile directories must be cleaned after each job; residual profile
  trees are guarded by `check_no_residual_sessions.py`.
