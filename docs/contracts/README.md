# Contracts

`openapi.json` in this directory is the **generated, committed** OpenAPI
document for the VeriDemand API. It is the single input for the frontend's
generated TypeScript types and Zod schemas.

## Regenerate

```bash
pnpm contracts:generate
```

This runs `scripts/generate_contracts.py` (writes `openapi.json`
deterministically) then `@hey-api/openapi-ts` (writes
`frontend/src/contracts/generated/`).

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
