# Phase 2 - Implementation report

- Date: 2026-07-22
- Branch: `phase/2-canonical-viewer-coordinates`
- Base tag: `phase-1-runtime-sessions-upload-queue-v1` (`c5691da479b5963a31c594fbba8dffa3664e404d`)
- Tag: `phase-2-canonical-viewer-coordinates-v1` (after final gate)

## Summary

Phase 2 delivers canonical PDF production for all accepted upload formats,
canonical HTTP delivery (full and ranged), page metadata, synthetic overlay
proof, normalised geometry contracts, a PDF.js viewer, and extended readiness for
LibreOffice and ReportLab. **No extraction** (native text, OCR, layout, LLM) is
performed.

See `docs/architecture/phase-2-canonical-documents.md` and ADRs 0008-0011.

## New / extended backend packages

| Area | Responsibility |
|---|---|
| `geometry/` | Normalised coordinate models (re-export contracts), rotation, bbox clamp |
| `canonical/` | TXT/image/PDF/Word producers, inspection, LibreOffice service, processor |
| `api/v1/endpoints/canonical.py` | Canonical PDF, metadata, overlay-proof |
| `health/service.py` | LibreOffice, ReportLab, canonical storage readiness |
| `processing/coordinator.py` | Canonicalisation worker (replaces admission-only stub) |

New contracts: `geometry.py`, `canonical.py`; extended `documents.py`, `errors.py`,
`progress.py`.

## API surface additions (`/api/v1`)

- `GET /sessions/{id}/documents/{doc}/canonical` (200 / 206 / 416 / 409)
- `GET .../canonical/metadata`
- `GET .../canonical/overlay-proof`

## Frontend

`frontend/src/features/viewer/`: PDF.js canvas viewer, scale toolbar, overlay
proof rendering. Session workspace integrates canonical view when
`canonical_view_available`.

## Dependencies

| Package | Version | Licence | Role |
|---|---|---|---|
| reportlab | 4.5.1 | BSD | Deterministic TXT/image → PDF |
| pdfjs-dist | 6.1.200 | Apache-2.0 | In-browser canonical PDF viewer |
| LibreOffice | 26.2.4.2 (local Windows) | MPL-2.0 | Headless DOC/DOCX → PDF (runtime) |

**Confirmed:** no OCR, HTR, or vision-model Python/Node dependencies added.

## Configuration

`.env.example` extended with LibreOffice path/timeout, canonicalisation workers,
TXT/image canonical settings, viewer scale limits, cache-control.

## Test counts

- Backend (pytest): **157 passed**.
  - New Phase 2 suites: geometry, TXT/image/PDF canonicalisation, LibreOffice
    discovery+DOCX conversion, canonical API (including byte-range), coordinator.
- Frontend unit (Vitest): **96 passed**.
- Frontend production build: passed (PDF.js worker bundled from installed package).
- E2E: Phase 1 specs updated; `canonical-viewer.spec.ts` added for viewer flows.

## Residual-data verification

`scripts/check_no_residual_sessions.py` fails on surviving `ses_*` directories,
`*.pdf.part` files, `staging/libreoffice/` leftovers, and short `lo/` workspaces.

## CI

Both CI jobs install `libreoffice-writer` before tests. `check_all.py` verifies
LibreOffice availability before pytest.

## Known limitations

- Single canonicalisation worker (hard-capped at 1).
- Word conversion fidelity depends on host LibreOffice version and fonts.
- On Windows, long UserInstallation paths are routed through short
  `<TEMP_ROOT>/lo/<hash>/` workspaces (PDF still published under session
  `canonical/`).
- Overlay proof is synthetic only; no real extraction spans.

## Phase 2.1 corrective note (PDF.js blank pages)

Tag `phase-2-canonical-viewer-coordinates-v1.1` adds packaged `pdfjs-dist` WASM
codecs at `/pdfjs-wasm/`, CORS expose headers for range responses, and viewer
render cancel-and-await / generation-token recovery. See ADR 0012 and
`docs/phases/phase-2-pdfjs-blank-pages-investigation.md`. Private corpus PDFs
remain gitignored under `fixtures/private/` only.

## Phase boundary confirmation

No native-text trust gate, OCR, layout analysis, handwriting classifier, vision
LLM, database, Redis, Celery, or authentication code was added. Phase 3 was not
started.
