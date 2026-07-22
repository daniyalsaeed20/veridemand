"""Synthetic PDF regression smoke corpus helpers."""

from __future__ import annotations

__all__ = [
    "CRITICAL_SUBSET",
    "EXPECTED_MANIFEST_SHA256",
    "EXPECTED_PDF_SHA256",
    "PHASE4_SUBSET",
]

CRITICAL_SUBSET: tuple[str, ...] = (
    "T01",
    "T05",
    "T10",
    "T14",
    "T20",
    "T21",
    "T41",
)

# Phase 4 printed OCR / visibility / scan pages (handwriting and LLM remain skipped).
PHASE4_SUBSET: tuple[str, ...] = (
    "T10",
    "T11",
    "T12",
    "T13",
    "T18",
    "T19",
    "T50",
    "T52",
)

# Keep in sync with docs/smoke/README.md.
EXPECTED_PDF_SHA256 = "373177016F10A6BA04142197F9A434AF8365493783F873C02B4E35889EC4FEA7"
EXPECTED_MANIFEST_SHA256 = "51514FCE918A4FAA5102BF65C37618D99162DB861F7BD16175A511DA016B7845"
