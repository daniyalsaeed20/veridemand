# fixtures/synthetic

Synthetic, non-sensitive documents generated for deterministic tests. No private
or PII-bearing documents are ever committed here (those live under the
git-ignored `fixtures/private/`).

## uploads/ — Phase 1 upload-validation corpus

`uploads/` holds a small corpus exercising every supported format and rejection
path of the Phase 1 upload pipeline. Each file is generated deterministically by
[`generate_uploads.py`](generate_uploads.py); regenerate and audit with:

```bash
.venv/Scripts/python.exe -m fixtures.synthetic.generate_uploads
```

`uploads/MANIFEST.json` records, per fixture, the expected outcome
(`accepted` or `rejected`) and the stable lowercase `error_code` (matching
`backend.app.contracts.errors.ErrorCode`). Backend tests parametrise over the
manifest, so it is the single source of truth for expected behaviour.

Coverage includes:

- **Accepted**: single/multi-page PDF, PNG/JPEG/BMP/WebP, multi-frame TIFF,
  UTF-8 and UTF-16 text, a minimal WordprocessingML `.docx`, a `.docx` with an
  external relationship (warning marker), and a synthetic minimal OLE2 `.doc`.
- **Rejected**: encrypted PDF, corrupt PDF, signature/extension mismatches,
  empty file, binary-in-text, control-character text, unsupported extension,
  macro `.docx` (via `vbaProject.bin` and via macro-enabled content type),
  path-traversal `.docx`, non-WordprocessingML `.docx`, malformed ZIP `.docx`,
  and a non-OLE `.doc`.

### `.doc` note

The valid `.doc` fixture is a hand-built minimal OLE2/CFB compound file
containing a `WordDocument` stream and no macros — sufficient for the structural
and macro-scan checks without shipping any real document. Boundary conditions of
the `oletools` macro scanner that are impractical to reproduce with a tiny
synthetic file are covered by mocking in the backend tests rather than by
additional binary fixtures.

## smoke/ — combined PDF regression corpus

`smoke/` holds the VeriDemand synthetic PDF regression corpus (combined PDF +
manifest). Documentation, checksums, and runner commands live under
[`docs/smoke/README.md`](../../docs/smoke/README.md). Run with
`pnpm smoke:corpus` against a live API.
