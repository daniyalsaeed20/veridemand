# Remediation Part 1 — Human Review Tooling

**Branch:** `remediation-01-extraction-acceptance`  
**Base Part 1 commit:** `e0c0d0081a32fe3fb898df352f3e8c6022452a34`  
**Date:** 2026-07-21  

**Verdict:** `CORPUS REVIEW TOOL READY — HUMAN REVIEW PENDING`

---

## Purpose

Replace the read-only `file:///` review index with a localhost annotation application so a reviewer can inspect pages, correct transcripts, review order/geometry, resolve critical anchors, and save annotations—without editing JSON by hand and without changing production extraction.

---

## New case-folder discovery (safe aggregates)

Private discovery now covers approved project-local locations (case folders + intake + legacy example + forensic seeds).

| Safe aggregate | Count |
|----------------|------:|
| Matched corpus documents | **8** |
| Deduplicated physical files discovered | **21** (includes duplicates collapsed by hash) |
| Selected pages | **25** |
| Cases with matched docs | amini, ali_vs_thomas, jones |

Difficult police report: **included** (both pages). Intake copy and case-folder copy are hash-identical and represented **once** in the corpus (`ali_police`), with private multi-location metadata retained only under `tmp/`.

Police-report page IDs (safe aliases): `ali_police_p1`, `ali_police_p2` (badge anchor on page 2).

---

## Review application capabilities

- Bind: **127.0.0.1 only** (default port 8765)
- Launcher: `scripts/extraction_acceptance/start_review.cmd`
- URL: `http://127.0.0.1:8765/`
- Dashboard with filters (status, police/handwriting/corrupt OCR/tables, native/OCR)
- Page editor: zoom/pan, overlay toggles, transcript edit, reading-order reorder + issue flags, critical-field panel, plain-language questions, box draw/delete, Save / Save&Next, Mark human reviewed

### Overlay types

Native words, fresh OCR lines, SourceTokens, SourceSpans, human expected boxes, reading-order numbers.

### Prefill

Separate native and OCR streams labelled **UNVERIFIED MACHINE OUTPUT**. OCR-routed pages use forensic cache or live pinned OCR for private benchmark population only. Machine transcript is preserved on save and never auto-overwrites approved human text.

### Persistence

Server-side atomic JSON writes under the private review root; backups before overwrite; schema validation; etag/revision stale detection; path traversal rejected; no `localStorage` as SoT.

---

## Annotation / known-anchor status

| Item | Status |
|------|--------|
| Human-reviewed pages | **0** (tool ready) |
| Corpus gold | **false** |
| Client name / law-firm anchors | Seeded where applicable; human link pending |
| Badge/ID anchor | Seeded on `ali_police_p2` as `USER_CONFIRMED_ANCHOR` |

---

## Tests and safety

| Item | Result |
|------|--------|
| New review-app unit tests | Included in `test_extraction_review_app.py` |
| Prior Part 1 acceptance tests | Retained |
| Private outputs ignored | Pass |
| Production extraction / OCR / contracts / parsers | **Unchanged** |
| OCR engine selection / upgrade | **None** |
| GPT / cloud OCR | **None** |
| Phase 6 / Part 2 | **Not started** |
| Tag | **Not created** |

---

## Next action for the user

1. Run `scripts\extraction_acceptance\start_review.cmd`
2. Open `http://127.0.0.1:8765/`
3. Start with `ali_police_p2` (badge/ID corrupt-embed review)
4. Mark pages human reviewed only when completeness gates pass

Stop — do not begin Remediation Part 2 from this report alone.
