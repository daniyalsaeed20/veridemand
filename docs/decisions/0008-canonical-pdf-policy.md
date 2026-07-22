# ADR 0008 - Canonical PDF policy

- Status: Accepted
- Date: 2026-07-22
- Phase: 2

## Context

Downstream extraction needs a single, inspectable PDF view per document with
stable page geometry. Uploads arrive as PDF, text, images, or Word formats.

## Decision

- Every accepted document is canonicalised to **one PDF** under
  `canonical/<document_id>.pdf`.
- **Original PDFs** are verified (readable, unencrypted, ≥ 1 page) and published
  **byte-identically** — no re-render or normalisation pass.
- **TXT** is rendered deterministically to US Letter via ReportLab (fixed metadata,
  Helvetica, normalised newlines). Unsupported glyphs fail with
  `canonicalisation_unsupported_text_glyph`.
- **Images** become one PDF page per frame (multi-frame TIFF only); WebP animation
  is rejected.
- **DOC/DOCX** convert through headless LibreOffice Writer to PDF (ADR 0009).
- Publication is **atomic**: stage → inspect → SHA-256 → `os.replace`; in-progress
  files use a `.pdf.part` suffix.
- Canonical PDFs are **session-scoped** and deleted with the session; no long-term
  archive.

## Consequences

- Viewers and overlays always target PDF page boxes from inspection metadata.
- Deterministic TXT/image producers enable regression hashing; original PDFs preserve
  user bytes.
- Word conversion quality depends on the installed LibreOffice version (recorded in
  metadata).
