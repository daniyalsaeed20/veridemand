# OCR Feasibility Spike (isolated)

**Not production architecture.** Disposable experiment for Pre-Implementation Readiness.

## Stack

- pdfplumber — native word extraction
- pypdfium2 — page render for OCR
- PaddleOCR — printed-text OCR
- Pillow / OpenCV — overlay + optional preprocess
- psutil — peak RSS sampling

## Run

```text
# Preferred: isolated venv (pinned PaddleOCR 2.7 / Paddle 2.6)
..\..\.tools\python312\python.exe -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe run_benchmark.py
```

**Note:** PaddleOCR 3.x + Paddle 3.3 failed on this Windows host with a oneDNN/PIR `NotImplementedError`. The spike pins 2.7.3 for feasibility measurement. Re-evaluate 3.x before production Phase 3.

Outputs land in `out/` (metrics JSON, overlays). Do not promote low-confidence tokens to verified facts.
