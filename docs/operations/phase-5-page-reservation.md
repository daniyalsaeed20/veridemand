# Phase 5 — Page reservation operations

## Profiles

| Profile | Enabled | Mode |
|---------|---------|------|
| Normal / default / Phase 4 production | `false` | `conservative` |
| Phase 5 acceptance | `true` | `conservative` |

```text
HANDWRITING_PAGE_VISION_FALLBACK_ENABLED=false
HANDWRITING_PAGE_VISION_FALLBACK_MODE=conservative
```

Unsupported modes (for example `hybrid`) fail settings validation. Do not
silently fall back.

## Operator environments

Run feature-off regression and feature-on acceptance in the **OCR-only**
environment (no Torch). See `docs/operations/phase-5-model-setup.md`
§ Windows environments.

```powershell
$env:UV_PROJECT_ENVIRONMENT = ".venv-ocr"
uv sync --group ocr
```

### Launch commands

| Command | OCR env | Phase 5 conservative reservation |
|---------|---------|----------------------------------|
| `pnpm dev` / `pnpm dev:ocr` | `.venv-ocr` | **Off** (release default) |
| `pnpm dev:phase5` | `.venv-ocr` | **On** (`ENABLED=true`, `MODE=conservative`) |

Do not use `pnpm dev:ocr` when validating Phase 5 routing — the Backend health
card shows `page_vision_off` vs `page_vision_on` so the active profile is
obvious. Hybrid mode is never enabled by these launchers.

Do not mix `model-dev` into this environment on Windows.

## Readiness

Enabling conservative page reservation does **not** require:

- handwriting classifier package
- server detector
- OpenAI / vision provider configuration

`openai_vision` remains `not_configured`. The app may be ready to reserve pages
while still unable to perform Phase 6 transcription.

## Acceptance

```text
uv run --group ocr python scripts/phase5/page_vision_reservation_acceptance.py
```

Requires private corpus artefacts under `fixtures/private/phase5/` and the
gitignored Task C2 page audit JSONL. Reports aggregates only.

## Cleanup

Reserved pages use existing session-owned visual results JSON and the canonical
PDF. Session TTL / cancellation cleanup removes them with the session tree.
