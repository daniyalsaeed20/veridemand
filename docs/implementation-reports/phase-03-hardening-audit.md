# Phase 3 Hardening Independent Re-Audit — B-01 / B-02 / B-03

**Audit date:** 2026-07-20  
**Auditor:** Fresh independent verification (not the hardening implementer)  
**Method:** Clean tip verification + authoritative doc/contract review + OCR init state-machine review + DELETE tombstone/drain/barrier inventory + deterministic race/stress suites + under-detection gate analysis + synthetic matrix + police page 4 probe + reference-package aggregates (aliases only) + pin/import-boundary regression + RSS/latency probe + contract dual-regen + full `check-all`

**Constraints honored:** No production code changes. No Phase 4 work. No Git tag create/move/delete. Audit probes lived only under gitignored `tmp/audit/`. Shared OCR model cache was not deleted.

---

## Final verdict

# PASS

The audited commit is suitable for the immutable tag `phase-03-audited-pass`.

Commit `4c6672e5e8064d697cb0cf229841a3f1f3b73e56` is suitable for the immutable tag `phase-03-audited-pass`.

All three blocking findings from the failed Phase 3 audit are closed:

1. **B-01** — OCR initialization is a retriable process-wide state machine (`uninitialized` → `initializing` → `ready` / `retry_wait`); failure no longer permanently poisons the adapter.
2. **B-02** — Session DELETE uses tombstone → cancel → drain → idempotent cleanup; controlled stress showed **100× HTTP 204**, **0× HTTP 500**, zero orphan workspaces.
3. **B-03** — Ink-rich under-detection demotes to `ocr_failed` + `insufficient_coverage` with suppressed tokens; police page 4 is no longer `ocr_usable`.

No blocking regressions. No Phase 4 scope introduced. Do **not** begin Phase 4 in this step; create the tag only via the separate immutable tagging procedure.

---

## Exact audited commit

| Field | Value |
|-------|-------|
| Branch | `phase-03-audit-hardening` |
| **Audited tip** | `4c6672e5e8064d697cb0cf229841a3f1f3b73e56` |
| Tip subject | `fix(phase-03): close audit blockers B-01, B-02, and B-03` |
| Working tree at audit start | Clean |
| Working tree after probes | Clean of production changes; only intentional new report file + gitignored `tmp/audit/` |

### Baseline

| Field | Value |
|-------|-------|
| Tag | `phase-02-audited-pass` |
| Peeled commit | `8930b3259cc076e1c308eefb24cb69f8a79bd08e` |
| Unchanged | **Yes** |
| Ancestor of audited tip | **Yes** |

### Related history (`982651a..HEAD`)

| Commit | Role |
|--------|------|
| `7a140dcc0df937d5ed97220ef0f122409818829c` | Failed audit evidence — [`phase-03-audit.md`](./phase-03-audit.md) preserved |
| `4c6672e5e8064d697cb0cf229841a3f1f3b73e56` | Hardening under audit — [`phase-03-hardening.md`](./phase-03-hardening.md) |

### Prior tags (unchanged)

`phase-00-pass`, `phase-01-pass`, `phase-01-audited-pass`, `phase-02-audited-pass`

---

## 1. Git and scope

| Check | Result |
|-------|--------|
| `HEAD` == `4c6672e5e8064d697cb0cf229841a3f1f3b73e56` | **PASS** |
| Working tree clean before audit | **PASS** |
| Descends from `phase-02-audited-pass` | **PASS** |
| Failed Phase 3 audit report committed | **PASS** (`7a140dc`) |
| Prior audited tags unchanged | **PASS** |
| Hardening diff limited to B-01/B-02/B-03 + contracts/config + tests + reports | **PASS** |
| No classification / fact extraction / chronology / billing interpretation / issue analysis engines / LLM / drafting / export runtime | **PASS** (contract stubs / settings flags only; no Phase 4+ services) |
| No private evidence, patient text, screenshots, OCR weights, credentials, or local absolute paths committed | **PASS** (reference binaries remain gitignored under `docs/example/`; weights outside repo) |

### Diff `982651a..4c6672e` (26 files)

OCR adapter state machine; session tombstone/drain; process write barriers; under-detection quality + preprocess inverse; AppSettings / taxonomies / contracts; FE under-detection messaging; unit/integration tests; `phase-03-audit.md` + `phase-03-hardening.md` + completion touch-up.

No unrelated feature work in the hardening commit.

---

## 2. B-01 — retriable initialization state machine

**Implementation:** [`backend/app/services/ocr/adapter.py`](../../backend/app/services/ocr/adapter.py)

| Requirement | Result |
|-------------|--------|
| One process-wide adapter | **PASS** |
| Exactly one init attempt at a time | **PASS** — leader + `_init_attempt_event` waiters |
| Concurrent callers wait for same attempt | **PASS** — `test_init_waiters_share_same_failure` |
| Failed attempt does not publish partial model | **PASS** — `_engine = None` on failure; publish only after full construct |
| Failed state does not permanently poison process | **PASS** — `RETRY_WAIT` + cooldown, then fresh attempt |
| Init future/reference cleared after failure | **PASS** — `_init_attempt_event = None` after wake |
| Later request can retry | **PASS** — `test_init_fail_then_succeed_same_process` |
| Cooldown configuration-driven and bounded | **PASS** — `ocr_init_retry_cooldown_ms` (default 2000) |
| Cooldown does not become permanent outage | **PASS** — monotonic clock + expiry allows retry |
| Successful init remains cached | **PASS** — `test_successful_init_cached_and_reused` |
| No two model instances initialize concurrently | **PASS** — `test_after_failure_exactly_one_retry_initializes` |
| Failed init releases worker capacity | **PASS** — `test_failed_init_releases_ocr_serialization` |
| Raw exception / model / cache paths not exposed | **PASS** — safe `OcrUnavailableError` messages; kinds only |
| `/api/v1/health` available when init fails | **PASS** — import-based `ocr_enabled`; status `ok` |

Independent unit run: `tests/unit/test_ocr_adapter.py` — **13 passed**.

Cooldown boundaries: `test_cooldown_blocks_retry_storm_then_allows` (blocks during cooldown; allows after). Time uses `time.monotonic()` (not wall-clock lockout).

`SHUTTING_DOWN` is terminal for the process lifetime until `reset_adapter_state()` (tests) or process restart — **by design**, not sticky poison after transient failure.

---

## 3. Cooldown and lifespan shutdown

| Check | Result |
|-------|--------|
| Cooldown begins only after genuine init failure | **PASS** |
| Requests during cooldown get retryable `OcrUnavailableError` | **PASS** |
| Kind distinguishes packages_missing / model_cache / transient / shutting_down | **PASS** |
| Cooldown expiry permits exactly one retry (single-flight) | **PASS** |
| Multiple callers at expiry do not storm | **PASS** |
| Successful init clears failure/cooldown | **PASS** |
| `shutdown_adapter()` via FastAPI lifespan `finally` | **PASS** — [`main.py`](../../backend/app/main.py) |
| Shutdown idempotent / mid-init safe | **PASS** — `test_shutdown_during_init_cleans_up` |
| Shutdown drops engine and wakes waiters | **PASS** |
| Adapter reset for subsequent test apps | **PASS** — `reset_adapter_state` in fixtures |

**Nonblocking:** no dedicated integration test that enters/exits a real ASGI lifespan solely to assert `shutdown_adapter`; unit + wiring review suffice for B-01 closure.

---

## 4. B-02 — tombstone lifecycle and job drain

**Implementation:** [`session/service.py`](../../backend/app/services/session/service.py), [`process/service.py`](../../backend/app/services/process/service.py), [`workspace.py`](../../backend/app/services/session/workspace.py)

### Authoritative DELETE order (verified)

1. Under lock: mark `DELETED` / `deleting`, bump `generation`, set `process_cancel_requested` + `cancel_event`
2. Outside lock: `after_mark_deleting` hook
3. Drain: `wait_until_idle(session_id)` (join process thread)
4. Idempotent `delete_workspace_tree` (missing = success; soft-fail residual locks — no HTTP 500)
5. Pop registry

| Check | Result |
|-------|--------|
| Tombstone visible before FS deletion | **PASS** |
| Retrieval APIs reject after tombstone | **PASS** — `_require_live_locked` → `SESSION_NOT_FOUND` |
| Uploads / process rejected for deleting session | **PASS** |
| Late worker cannot recreate session directory as live session | **PASS** — generation / deleting barriers |
| Already-missing paths = success | **PASS** |
| Double DELETE → 204 × 2 | **PASS** |
| Explicit TTL sweeper uses drain path | **PASS** — `_expire_session` |
| Jobs registered before work; `finally` unregisters | **PASS** |
| Drain does not hold session lock while joining | **PASS** |
| Late OCR cannot commit after tombstone | **PASS** — `_commit_ocr_page` / `_may_write` |

### Write / final-commit barriers

Audited paths: normalize mkdir/write, thumbnail save, OCR page commit (tokens/spans/meta/status), process events after OCR. Each final OCR commit re-checks generation, `deleting`, `DELETED`, document presence. Failed validation discards results (no publish).

**Nonblocking residual:** `_expire_locked` (invoked while already holding the session lock from `_require_live_locked` on TTL) still performs `rmtree` without drain. Explicit DELETE and the sweeper use the drained path that closed B-02. Treat as a follow-up hardening item, not a reopen of the audited DELETE-during-process failure mode.

---

## 5. DELETE stress and filesystem cleanup

Independent run: `tests/integration/test_delete_process_races.py` — **4 passed**.

| Suite | Result |
|-------|--------|
| DELETE during normalize (barrier) | **204**; no orphan tree |
| DELETE before OCR commit (barrier) | **204**; commit discarded |
| Double DELETE | **204** × 2 |
| Stress 100 iterations | **100 × 204**; **0 × 500**; zero orphans |

Stress harness: ~⅓ of iterations hold at `before_workspace_write` and release on `after_mark_deleting` (hits the audited Windows lock race); remaining iterations delete without barrier (early/mid process). Harness is barrier-controlled rather than purely random timing — **adequate** to close the previously failing pattern; noted as nonblocking evidence-depth gap.

Filesystem cleanup: path confined under `temp_root` via `ensure_descendant`; up to 5 OSError retries; final `ignore_errors` soft path. Unit: `test_delete_workspace_idempotent` present. New sessions remain operational after stress (fresh `make_client` per iteration).

---

## 6. B-03 — under-detection quality gate

**Implementation:** [`ocr_quality.py`](../../backend/app/services/extraction/ocr_quality.py), [`ocr_page.py`](../../backend/app/services/extraction/ocr_page.py)

| Property | Result |
|----------|--------|
| Page-level | **PASS** |
| Deterministic | **PASS** |
| Independent of filename / provider / identity | **PASS** |
| `insufficient_coverage` canonical | **PASS** — contracts + taxonomies + FE |
| Multi-signal (≥2 of coverage / token floor / coverage-to-ink / band concentration) | **PASS** |
| Dark pixels alone cannot fail | **PASS** |
| Token count alone cannot fail | **PASS** (requires ink-rich gate) |
| Mean confidence alone cannot pass under-detected page | **PASS** — under-detection forces `ocr_failed` before conf ladder |

### Signals / thresholds (material)

| Signal / setting | Default / note |
|------------------|----------------|
| `ocr_min_ink_for_coverage_check` | 0.08 |
| `ocr_min_token_coverage` | 0.05 |
| `ocr_min_coverage_to_ink_ratio` | 0.15 |
| `ocr_min_tokens_ink_rich` | 25 |
| `ocr_ink_binarize_threshold` | 200 |
| `ocr_under_detection_triggers_retry` | true |
| Band concentration | ≥0.85 with ink ≥0.12 (**hardcoded** — nonblocking) |

### Publish semantics for under-detection

| Check | Result |
|-------|--------|
| Not `ocr_usable` | **PASS** |
| `ocr_status=failed` | **PASS** — closed vocab; enables Retry |
| Tokens/spans suppressed | **PASS** |
| Amber issue `extraction.insufficient_ocr_coverage` | **PASS** |
| Page remains manually viewable | **PASS** — FE + canonical PDF path |
| UI does not imply blank | **PASS** — “insufficient coverage — review required” |
| Confidence not factual certainty | **PASS** — FE copy |

`failed` vs a separate `review_required` status: contracts keep `ocr_status` closed (`not_needed|pending|done|failed`). Under-detection correctly uses `failed` + quality flag + amber issue + FE “review required” wording — **contract-consistent**, not a silent mismatch.

---

## 7. Police page 4

Independent probe: `tmp/audit/police_page4.json` (alias `police` / EG90156; aggregates only).

| Field | Value |
|-------|-------|
| Route | `ocr` |
| Dimensions (200 DPI) | 1700 × 2219 |
| Dark-pixel fraction | ≈ 0.335 |
| Outcome | **`ocr_failed`** |
| Under-detection | **true** |
| Quality flags | `insufficient_coverage` |
| `ocr_status` | `failed` |
| Published tokens / spans | **0 / 0** |
| Pre-suppress mean confidence | ≈ 0.952 |
| Coverage | ≈ 0.008 |
| Retried | **true** (retry DPI 300) |
| Marked `ocr_usable` | **false** |
| Manually viewable | **true** |
| Elapsed (cold-ish path) | ≈ 8.1 s |

**Required result met.** Safe failure accepted; page need not become successfully OCR-readable.

---

## 8. Deskew inverse geometry

| Check | Result |
|-------|--------|
| Forward affine retained on preprocess | **PASS** |
| Inverse applied to OCR polygons before normalize | **PASS** — `ocr_page.py` |
| Unit affine round-trip | **PASS** — `test_deskew_inverse_maps_polygon_back` |
| Synthetic skew angles (−8…+8°) inverse err &lt; 1e−3 | **PASS** — `tmp/audit/under_detection_matrix.json` |
| First-pass / retry not mixed | **PASS** — atomic choose-then-`_finalize` |
| Normalized coords remain in `[0,1]` via existing normalize | **PASS** (pipeline) |

**Nonblocking:** no interactive browser overlay verification (PDF.js zoom / resize / HiDPI) in this audit session. Coordinate unit + preprocess inverse evidence is sufficient for B-03 geometry closure; visual QA remains a follow-up.

---

## 9. Under-detection regression suite

| Suite | Result |
|-------|--------|
| `test_ocr_under_detection.py` (5 tests) | **PASS** |
| Auditor synthetic matrix (`tmp/audit/under_detection_matrix.json`) | **`all_expect_pass: true`** |

| Case | Expected | Observed |
|------|----------|----------|
| Dense good OCR | usable / not under | PASS |
| Dense sparse mocked (police-like) | under / failed | PASS |
| Sparse six-token low ink | not under | PASS |
| Form dark boxes + many words | not under | PASS |
| Photo-heavy few words + high ink | under | PASS |
| Header-only / quadrant-only + dense ink | under | PASS |
| Table / multi-column good | not under | PASS |
| Boundary below / above ink gate | as expected | PASS |
| No structured facts produced | N/A Phase 3 | PASS |

---

## 10. Bounded retry policy

| Check | Result |
|-------|--------|
| At most one preprocess+OCR retry | **PASS** |
| Under-detection triggers retry when configured | **PASS** |
| Retry score prefers coverage over confidence-alone | **PASS** |
| Worse retry does not replace better first pass | **PASS** (score compare) |
| DPI bounded via settings | **PASS** — render 200 / retry 300 |

---

## 11. Initialization × deletion interaction

| Case | Result |
|------|--------|
| Per-session cancel Event on DELETE | **PASS** — does not clear shared ready engine |
| Failed init does not block session cleanup | **PASS** — soft cleanup / 204 path |
| Late results discarded after tombstone | **PASS** — commit barriers |
| Shutdown during / after cooldown | **PASS** — `SHUTTING_DOWN` |

---

## 12. Regression — prior Phase 3 behavior

| Check | Result |
|-------|--------|
| PaddleOCR **2.7.3** / PaddlePaddle **2.6.2** pinned | **PASS** |
| Sole production `from paddleocr import PaddleOCR` in `adapter.py` | **PASS** (AST scan) |
| OCR max inflight = 1 | **PASS** |
| PDFium max inflight = 1 | **PASS** — concurrency tests |
| Lock order (PDFium released before OCR) | **PASS** — design + Phase 3 tests |
| eCW medical 24/24 native | **PASS** |
| eCW billing OCR + warning | **PASS** — 136 tokens, warn path |
| Good OCR coordinates still highlight (pipeline unchanged for usable pages) | **PASS** (no regression in usable path) |
| Session isolation | **PASS** |

---

## 13. Reference-package regression (aliases only)

Independent run of `backend/scripts/phase03_reference_acceptance.py` → `tmp/audit/phase03_reference_acceptance.json`:

| Alias | native | ocr_routed | ocr_ok | warn | fail | tokens |
|-------|--------|------------|--------|------|------|--------|
| ecw_medical | 24/24 | 0 | — | — | — | 0 |
| ecw_billing | 0 | 1 | 1 | 1 | 0 | 136 |
| police (first 4) | 3 | 1 | 0 | 0 | **1** | **0** |
| insurer | 1 | 0 | — | — | — | — |
| long_medical (sample 6) | 6 | 0 | — | — | — | — |

Matches hardening report aggregates. Police OCR page now **fails** with suppressed tokens (was incorrectly usable pre-hardening).

**Nonblocking carryover (N-02):** `long_medical` alias patterns still resolve eCW medical first (6 native pages), not the Jackman stack. Documented previously; does not reopen B-01/B-02/B-03.

---

## 14. Performance and memory

Independent probe `tmp/audit/resource_during_ocr.json` (police page 4 path):

| Metric | Value |
|--------|-------|
| Cold init | ≈ 5.3 s |
| Warm reuse | ≈ 0 ms (cached) |
| OCR page (incl. under-detect retry) | ≈ 3.1 s (warm engine) |
| RSS after init | ≈ 416 MB |
| RSS after OCR page | ≈ 644 MB |
| Peak working set | ≈ **788 MB** |
| Shutdown | ≈ 104 ms |

Prior Phase 3 audit cited ≈ 828 MB peak RSS; hardening cited ≈ 662 MB after model load. Independent peak ≈ 788 MB — **no material unexplained growth**.

DELETE stress (100 iters) completed without orphan accumulation; post-stress apps create cleanly.

---

## 15. API and frontend

| State | Behavior |
|-------|----------|
| OCR init unavailable / cooldown | `OcrUnavailableError` → contracted extraction failure path; no path leakage |
| Session deleted during process | **204**; subsequent GETs **404** `session_not_found` |
| FE stops treating session as live on 404 / `session_not_found` | **PASS** — [`App.tsx`](../../frontend/src/app/App.tsx) clears session |
| `insufficient_coverage` | Visible “review required”; Retry enabled; tokens not selectable as complete evidence |
| Health during init failure | **ok** |

No expected lifecycle path forced to raw HTTP 500 in the audited DELETE/OCR suites.

---

## 16. Contract and generation

| Check | Result |
|-------|--------|
| `insufficient_coverage` in document-page contract | **PASS** |
| `extraction.insufficient_ocr_coverage` in issue-types + taxonomies | **PASS** |
| Under-detection / cooldown knobs in AppSettings + schema + Zod | **PASS** |
| Dual regen + `check-contracts` | **PASS** — no drift |
| Regenerated twice with no content drift vs tip | **PASS** |

---

## 17. Clean verification

Independent `node scripts/check-all.mjs` on tip:

| Gate | Result |
|------|--------|
| Backend ruff format / check | PASS |
| Backend mypy | PASS |
| Backend pytest | **164 passed** |
| Frontend format / lint / typecheck | PASS |
| Frontend vitest | **9 passed** |
| Frontend production build | PASS |
| Contract drift | **none** |
| Drift-proof script | PASS |

Minimum counts met (backend ≥164, frontend ≥9). No reduction.

---

## 18. Blocking defects

**None.**

B-01, B-02, and B-03 from [`phase-03-audit.md`](./phase-03-audit.md) are closed on this tip.

---

## 19. Nonblocking gaps

| ID | Note |
|----|------|
| N-01 | `_expire_locked` still rmtree without drain under the session lock (in-lock TTL path); explicit DELETE/sweeper are safe |
| N-02 | `long_medical` alias collision with eCW medical (carryover) |
| N-03 | Band-concentration thresholds (0.85 / 0.12) hardcoded, not AppSettings |
| N-04 | DELETE stress is barrier-controlled, not fully random OS scheduling |
| N-05 | No browser visual overlay QA for deskew after zoom/resize/HiDPI in this audit |
| N-06 | No dedicated ASGI lifespan integration test for `shutdown_adapter` |
| N-07 | Under-detection knobs remain `0.1-provisional` (documented) |
| N-08 | Process-global OCR cancel API remains; production DELETE uses per-session Event |

None of these reopen B-01/B-02/B-03 or block `phase-03-audited-pass`.

---

## 20. Stop condition

**Stop.** Do **not** begin Phase 4 in this step.

Create `phase-03-audited-pass` only via the separate immutable tagging procedure pointing at:

`4c6672e5e8064d697cb0cf229841a3f1f3b73e56`
