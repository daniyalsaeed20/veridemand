# Dependency security review

How VeriDemand checks and records dependency vulnerability evidence for the
monorepo. Purpose/version/licence inventories remain in
[direct-dependencies.md](direct-dependencies.md) and
[licence-inventory.md](licence-inventory.md). The root
[DEPENDENCY_INVENTORY.md](../../DEPENDENCY_INVENTORY.md) points here.

## Python lockfile integrity

Confirm the committed `uv.lock` matches project metadata:

```bash
uv lock --check
```

A non-zero exit means the lockfile is stale or drifted — regenerate with
`uv lock` only after intentional dependency changes, and update the inventory
docs in the same change.

## Frontend production audit

```bash
pnpm audit --prod
```

Triage findings for production transitive packages. Dev-only advisories may be
tracked separately and must not force unrelated production dependency churn.

## Python vulnerability triage

Python package advisories are reviewed against the locked set from `uv.lock`
(and optional `ocr` group packages when OCR is in scope). Triage notes record
severity, affected package/version, exploitability in VeriDemand’s use, and
disposition (upgrade, mitigate, accept with rationale).

Do **not** add unpinned audit scanners as production runtime dependencies.
Optional developer tooling stays out of the production install set unless
explicitly inventoried with purpose, version, and licence.

## Phase 4 OCR optional group

When reviewing Phase 4, include optional `ocr` group packages (`paddleocr`,
`paddlepaddle`, related transitive wheels) in triage even though they are not
required for every deploy. Model files under `.models/` are assets, not PyPI
packages; record model licence notes in the licence inventory at bootstrap
time.

## Results recorded during Phase 4 final consolidation

| Scan | Command | Date | Result summary | Disposition |
|------|---------|------|----------------|-------------|
| uv lock | `uv lock --check` | 2026-07-29 | Lock matches metadata (105 packages resolved) | Accept |
| pnpm prod audit | `pnpm audit --prod` | 2026-07-29 | No known vulnerabilities found | Accept |
| Python advisories | Locked set + OCR group review | 2026-07-29 | No unpinned audit tool added; no reachable critical finding requiring upgrade during consolidation | Accept — no speculative stack upgrade |

Contract hashes (SHA-256) after double `pnpm contracts:generate`:

| Artifact | SHA-256 |
|----------|---------|
| `docs/contracts/openapi.json` | `38a7b4c395a0e8a88e1559a291d29df64c642f57e62945f36d91a44d09c35cde` |
| `frontend/src/contracts/generated/types.gen.ts` | `86ee581f1c30ea0a9828b31192742ef04aaecc61c1091c55e937aa329be8d6da` |
| `frontend/src/contracts/generated/zod.gen.ts` | `53618469156059b457dc24ec0ad02dae1f1914e4f201262cbcf006e03c63e7a3` |

Notes from the consolidation run (opaque; no document text):

- Second contract generation produced no diff versus the first.
- Frontend `viewerApi.ts` retains a minimal generated `zQueueInfo` extend for
  scheduler fields until generated OpenAPI covers the same shape without a bridge.
- `FAIR_OCR_PAGE_CHUNK_SIZE` remains a documented deprecated migrator (not silent).

## Phase 5 Task 2 additions

| Scan | Command | Date | Result summary | Disposition |
|------|---------|------|----------------|-------------|
| uv lock | `uv lock --check` | 2026-07-31 | Lock includes onnxruntime 1.28.0 + onnx 1.22.0 (model-dev) | Accept |
| Boundary | `scripts/check_dependency_boundary.py` | 2026-07-31 | onnxruntime/onnx allowlisted narrowly; openai/cv2/HTR still forbidden | Accept |

ONNX Runtime performs **local** CPU inference only. No Phase 5 provider network
call. No compliance claim.

## Related

- [phase-4-security-review.md](../security/phase-4-security-review.md)
- [phase-5-security-review.md](../security/phase-5-security-review.md)
- [licence-inventory.md](licence-inventory.md)
