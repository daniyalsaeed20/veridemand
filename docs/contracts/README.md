# Contracts

`openapi.json` in this directory is the **generated, committed** OpenAPI
document for the VeriDemand API. It is the single input for the frontend's
generated TypeScript types and Zod schemas. Phase 4 public contracts live under
`backend/app/contracts/`.

## Regenerate

```bash
pnpm contracts:generate
```

This runs `scripts/generate_contracts.py` (writes `openapi.json`
deterministically) then `@hey-api/openapi-ts` (writes
`frontend/src/contracts/generated/`).

## Phase 4 contracts

Visual OCR intermediate contracts live in `backend/app/contracts/visual.py` and
`ocr.py` (`VisualDocumentSummary`, `VisualPageResult`, `PrintedOcrLine` / word /
block). Document statuses include `visual_*` values; progress SSE includes Phase 4
visual events. Regenerate OpenAPI + Zod after any shape change.

## Verify (no drift)

```bash
pnpm contracts:check
```

Generates twice, compares hashes for determinism, and runs `git diff
--exit-code` on the committed contracts. CI runs this.

## Rules

- Do not edit `openapi.json` or `frontend/src/contracts/generated/` by hand.
- Change API shapes in `backend/app/contracts/`, then regenerate and commit.
- Generation is in-process (no running server) and contains no timestamps,
  machine paths, or environment-specific server URLs.
