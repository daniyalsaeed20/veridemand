# Phase 3 synthetic native-PDF fixtures

These deterministic, non-sensitive fixtures exercise native PDF extraction and
native-text trust-gate signals. Regenerate the committed PDFs from the repository
root with:

```powershell
$env:Path = "$env:USERPROFILE\.local\bin;" + $env:Path
uv run python fixtures/synthetic/native/generate_native.py
```

`generate_native.py` uses ReportLab in invariant mode. It uses `pypdf` to apply
page rotation and CropBox changes, and to write controlled raw text streams with
custom `ToUnicode` mappings for codepoints that ordinary ReportLab fonts cannot
reliably represent.

The bad-layer construction methods are:

- `replacement-character-layer.pdf`, `private-use-layer.pdf`, and
  `control-character-layer.pdf`: raw text streams map simple glyph codes to
  U+FFFD, private-use codepoints, and C0 control characters respectively.
- `duplicate-text-layer.pdf`: the same text is drawn 50 times at identical
  coordinates.
- `out-of-bounds-text-layer.pdf`: text is placed beyond both page corners, with
  one visible anchor string.
- `cid-token-layer.pdf`: visible literal `(cid:123)`-style strings.
- `symbol-noise-layer.pdf`: mostly punctuation-only lines.
- `corrupt-geometry-layer.pdf`: raw text matrices use zero text scale and
  negative horizontal scale, approximating zero-size and inverted character
  bounding boxes while retaining a structurally valid PDF.

All content is synthetic; no private, client, medical, or case-derived material
is included.
