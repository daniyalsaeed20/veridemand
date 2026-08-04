# Phase 5 labelling operations

## Task A2 — Targeted project handwriting seeds (current)

Prototype labelling found **0** handwritten crops. Task A2 collects ~100
human-confirmed handwritten regions from targeted private pages (not another
random 300-crop queue).

### 0. Backup

```bash
pnpm phase5:dataset:backup
```

### 1. Build the targeted page queue

```bash
pnpm phase5:handwriting-seeds:queue
```

Priority (metadata only; no model predictions): pages of prototype `uncertain`
crops, coverage-worklist pages, `police_form` pages, then heuristic form / sparse
pages. Billing-only pages are not auto-added.

### 2. Human seed collection (loopback)

```bash
pnpm phase5:handwriting-seeds:serve -- --reviewer handwriting_reviewer_01
```

URL:

```text
http://127.0.0.1:8767/?reviewer=handwriting_reviewer_01
```

Rules:

- Confirm only **clear** handwriting (cursive, hand-printed, digits, initials,
  signatures, corrections, form entries, notes).
- Draw a region, or select an existing clean crop, or draw a tighter subregion
  from an uncertain mixed crop (original crop/label unchanged).
- Do not transcribe. Do not record what the handwriting says.
- Mark **no usable handwriting** or **defer** when appropriate.
- No OCR text, confidence, predictions, filenames, or paths are shown.
- No `localStorage` / IndexedDB / service worker.
- Stop near ~100 valid regions or when candidates are exhausted.

### 3. After human collection

```bash
pnpm phase5:dataset:backup
pnpm phase5:handwriting-seeds:verify
pnpm phase5:handwriting-seeds:resolve
pnpm phase5:handwriting-seeds:report -- --write-aggregate docs/evaluation/phase-5-handwriting-seed-readiness.md
```

Do **not** train a model in Task A2.

## Default workflow (Task A) — prototype single-pass sample (completed)

Phase 5 classifies writing style for routing only. Prototype labels train a
local style classifier so handwritten/uncertain regions can later bypass Paddle
recognition (`reserved_for_vision` / `pending_phase_6`). Phase 5 does **not**
transcribe handwriting or call a vision provider.

See ADR 0053. Dual pilot review, full coverage correction, and the ~45k primary
queue remain available as **parked release-hardening** tools (ADR 0052) — they
are not mandatory before the first prototype classifier.

### 0. Backup private manifests

```bash
pnpm phase5:dataset:backup
```

### 1. Build the prototype queue (once)

```bash
pnpm phase5:labels:prototype-queue -- --queue-version phase5-prototype-primary-v1
```

Target: ~300 crops from the existing 600-crop pilot, seed 4101, excluding crops
on pages with active coverage-correction outcomes. Does not rebuild the full
corpus or authorise `full-primary`.

### 2. Single-pass prototype review (~300 crops)

```bash
pnpm phase5:labels:serve -- --queue prototype-primary --reviewer proto_reviewer_01
```

URL shape:

```text
http://127.0.0.1:8765/?role=primary&queue=prototype-primary&reviewer=proto_reviewer_01
```

One human reviewer. Ambiguous crops may be `uncertain`; unusable crops use
exclude. No second review is required for the prototype path.

After completion:

```bash
pnpm phase5:dataset:backup
pnpm phase5:labels:resolve
pnpm phase5:labels:prototype-report -- --write-aggregate docs/evaluation/phase-5-prototype-labels.md
```

## Parked — dual annotation pilot (release hardening)

Do **not** treat dual review as a blocker for prototype model development.

### Page-level coverage review (separate from script labels)

```bash
pnpm phase5:dataset:backup
pnpm phase5:coverage:build
pnpm phase5:coverage:verify
pnpm phase5:coverage:serve -- --reviewer cov_reviewer_01
```

Open `http://127.0.0.1:8766/?reviewer=cov_reviewer_01`. Coverage outcomes are
**not** script labels. Outstanding correction worklist entries are parked for
later corpus hardening (ADR 0053).

### Primary / secondary pilot (600 crops)

```bash
pnpm phase5:labels:serve -- --queue pilot-primary --reviewer rev_<opaque_id>
pnpm phase5:labels:serve -- --queue pilot-secondary --reviewer rev_<different_opaque_id>
```

The same `reviewer_id` **must not** serve both pilot primary and secondary roles.

```bash
pnpm phase5:labels:pilot-report
pnpm phase5:labels:adjudication
pnpm phase5:labels:resolve
pnpm phase5:dataset:report
```

## Full-corpus queue (parked)

The full primary queue (~45k canonical crops) remains preserved and marked:

```text
full primary queue — not authorised for review until pilot approval
```

Serving it requires an explicit flag:

```bash
pnpm phase5:labels:serve -- --queue full-primary --authorise-full-queue --reviewer rev_<opaque_id>
```

```bash
pnpm phase5:labels:queue -- --seed 42
```

Rebuilds the full primary queue only. It is **not** the default human task.

## Blind review rules

- UI shows the crop image and opaque `crop_id` only.
- No OCR text, confidence, filenames, case names, source paths, candidate
  provenance, sampling reasons, or model predictions.
- Events are append-only JSONL with crop SHA-256.
- No `localStorage` / browser persistence of private payloads.
- Quality flags (`crop_too_tight`, `requires_page_context`, …) do **not**
  auto-change the label.
- `requires_page_context` records that the blind crop was insufficient and
  routes to a separate context-review worklist — do not force a label.

## Label definitions

| Label | Meaning |
|-------|---------|
| printed | Machine-printed text style |
| handwritten | Handwriting style (including signatures) |
| uncertain | Ambiguous / vision-reserved; not initial three-class training-eligible |
| non_text | Borders, noise, logos, non-text marks |

### Printed

Select `printed` for mechanically rendered text, typed/computer-generated text,
printed form labels, clearly machine-generated digits, and machine-rendered
stamps.

### Handwritten

Select `handwritten` for cursive, hand-printed letters, handwritten digits,
initials, **signatures**, handwritten corrections, and handwritten form entries.
Signatures must be `handwritten` so they never enter local printed recognition.

### Uncertain

Select `uncertain` when printed and handwritten content cannot be separated, the
crop is too ambiguous, severe blur/damage prevents a reliable decision,
handwriting overlaps printed content, or page context would be required. Do not
force an uncertain crop into a model class.

### Non-text

Select `non_text` for empty boxes, rules/borders, check marks without
characters, icons, texture, image fragments, detector false positives, and
decorative marks without readable writing.

### Exclude

Use exclusion—not `uncertain`—when the crop file is broken, empty, geometry is
clearly wrong, the crop is so tight or broad that it is unusable, or the source
image failed to load.

Do not transcribe visible content. Do not type names, numbers, addresses, or
visible document text into notes.

### Keyboard

| Key | Action |
|-----|--------|
| `P` | printed |
| `H` | handwritten |
| `U` | uncertain |
| `N` | non_text |
| `S` | signature → handwritten |
| `X` | exclude |
| `Z` | skip |

## Related docs

- `docs/evaluation/phase-5-prototype-labels.md`
- `docs/evaluation/phase-5-handwriting-seed-readiness.md`
- `docs/evaluation/phase-5-annotation-pilot.md`
- `docs/evaluation/phase-5-source-group-adequacy.md`
- `docs/evaluation/phase-5-dataset-readiness.md`
- ADR 0051, ADR 0052, ADR 0053
