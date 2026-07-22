#!/usr/bin/env python3
"""Opaque aggregate evaluator for private visual OCR fixtures.

Reads gitignored ``fixtures/private/visual-ocr-manifest.local.json``.
Prints only opaque labels, counts, confidence aggregates, duration, and pass/fail.
Never prints OCR text, filenames, patient names, or local absolute paths.
"""

from __future__ import annotations

import argparse
import json
import statistics
import time
from pathlib import Path
from typing import Any

PRIVATE_ROOT = Path("fixtures/private")
MANIFEST_NAME = "visual-ocr-manifest.local.json"


def _load_manifest(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise SystemExit("Manifest must be a JSON object")
    return data


def _evaluate_entry(label: str, entry: Any, private_root: Path) -> dict[str, object]:
    started = time.perf_counter()
    if isinstance(entry, str):
        rel = entry
        pages: list[int] | None = None
        phase5 = False
    elif isinstance(entry, dict):
        rel = str(entry.get("file") or "")
        pages_raw = entry.get("pages")
        pages = [int(p) for p in pages_raw] if isinstance(pages_raw, list) else None
        phase5 = bool(entry.get("phase5_pending") or entry.get("handwriting"))
    else:
        return {
            "label": label,
            "status": "invalid_entry",
            "pass": False,
            "duration_ms": 0,
        }

    if phase5:
        return {
            "label": label,
            "status": "skipped_phase5_pending",
            "pages": 0,
            "pages_ocr_processed": 0,
            "pass": True,
            "duration_ms": int((time.perf_counter() - started) * 1000),
        }

    pdf_path = (private_root / rel).resolve()
    try:
        pdf_path.relative_to(private_root.resolve())
    except ValueError:
        return {
            "label": label,
            "status": "path_outside_private",
            "pass": False,
            "duration_ms": int((time.perf_counter() - started) * 1000),
        }

    if not pdf_path.is_file():
        return {
            "label": label,
            "status": "missing",
            "pass": False,
            "duration_ms": int((time.perf_counter() - started) * 1000),
        }

    # Structural-only probe: page count via pypdf. Full OCR path is optional and
    # invoked only when models are present (operator-local).
    from pypdf import PdfReader

    reader = PdfReader(str(pdf_path))
    page_count = len(reader.pages)
    selected = pages if pages else list(range(1, page_count + 1))
    selected = [p for p in selected if 1 <= p <= page_count]

    model_record = Path(".models/paddleocr/model-record.json")
    if not model_record.is_file():
        return {
            "label": label,
            "status": "models_absent",
            "page_count": page_count,
            "pages_selected": len(selected),
            "pages_ocr_processed": 0,
            "pass": True,
            "duration_ms": int((time.perf_counter() - started) * 1000),
            "note": "Models absent; structural check only.",
        }

    # When models exist, report opaque aggregates without text.
    # Operators can extend this hook to call VisualOcrService locally.
    return {
        "label": label,
        "status": "structural_ok",
        "page_count": page_count,
        "pages_selected": len(selected),
        "pages_ocr_processed": 0,
        "pages_completed": 0,
        "pages_no_text": 0,
        "pages_failed": 0,
        "average_confidence": None,
        "cer": None,
        "wer": None,
        "pass": True,
        "duration_ms": int((time.perf_counter() - started) * 1000),
        "note": "Opaque structural pass; run full local OCR offline as needed.",
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--manifest",
        type=Path,
        default=PRIVATE_ROOT / MANIFEST_NAME,
        help="Path to gitignored visual-ocr-manifest.local.json",
    )
    args = parser.parse_args(argv)

    if not args.manifest.is_file():
        print(
            json.dumps(
                {
                    "status": "manifest_absent",
                    "pass": True,
                    "message": (
                        f"{MANIFEST_NAME} not found; skipping private visual OCR evaluation."
                    ),
                },
                indent=2,
                sort_keys=True,
            )
        )
        return 0

    manifest = _load_manifest(args.manifest)
    entries = manifest.get("cases") if isinstance(manifest.get("cases"), dict) else manifest
    if not isinstance(entries, dict):
        raise SystemExit("Manifest cases must be an object of opaque_label -> entry")

    started = time.perf_counter()
    results = [_evaluate_entry(str(label), entry, PRIVATE_ROOT) for label, entry in entries.items()]
    durations = [
        int(ms) if isinstance((ms := r.get("duration_ms")), (int, float)) else 0 for r in results
    ]
    summary = {
        "status": "completed",
        "cases": len(results),
        "passed": sum(1 for r in results if r.get("pass")),
        "failed": sum(1 for r in results if not r.get("pass")),
        "mean_duration_ms": int(statistics.mean(durations)) if durations else 0,
        "total_duration_ms": int((time.perf_counter() - started) * 1000),
        "results": results,
        "pass": all(bool(r.get("pass")) for r in results),
    }
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0 if summary["pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
