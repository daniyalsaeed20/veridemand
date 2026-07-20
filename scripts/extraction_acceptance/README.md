# Extraction acceptance tooling

Remediation Part 1 — safe evaluation scripts only.

**EVALUATION SCHEMA — NOT YET PRODUCTION CONTRACT**

## Commands

```powershell
# Rebuild synthetic fixtures
backend\.venv\Scripts\python.exe scripts\extraction_acceptance\build_synthetic_fixtures.py

# Private corpus + review pack (gitignored under tmp/extraction-remediation/)
backend\.venv\Scripts\python.exe scripts\extraction_acceptance\build_corpus_manifest.py
backend\.venv\Scripts\python.exe scripts\extraction_acceptance\build_review_pack.py
backend\.venv\Scripts\python.exe scripts\extraction_acceptance\run_baseline.py
backend\.venv\Scripts\python.exe scripts\extraction_acceptance\validate_annotations.py
```

## Localhost annotation app

Do **not** open the review pack via `file:///`. Use:

```powershell
scripts\extraction_acceptance\start_review.cmd
```

Or:

```powershell
backend\.venv\Scripts\python.exe scripts\extraction_acceptance\start_review_server.py
```

Then open **http://127.0.0.1:8765/** (bound to localhost only).

Private convenience launcher is also written to `tmp/extraction-remediation/acceptance-review/start_review.cmd` when the pack is built.

Do not commit `tmp/extraction-remediation/`.
