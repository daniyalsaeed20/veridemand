# Extraction acceptance tooling

Remediation Part 1 — safe evaluation scripts only.

**EVALUATION SCHEMA — NOT YET PRODUCTION CONTRACT**

## Commands

```powershell
# Rebuild synthetic fixtures
backend\.venv\Scripts\python.exe scripts\extraction_acceptance\build_synthetic_fixtures.py

# Private corpus (gitignored outputs under tmp/extraction-remediation/)
backend\.venv\Scripts\python.exe scripts\extraction_acceptance\build_corpus_manifest.py
backend\.venv\Scripts\python.exe scripts\extraction_acceptance\build_review_pack.py
backend\.venv\Scripts\python.exe scripts\extraction_acceptance\run_baseline.py
```

Do not commit `tmp/extraction-remediation/`.
