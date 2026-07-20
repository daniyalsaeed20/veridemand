# Phase 3 Hardening Report — B-01 / B-02 / B-03

**Status date:** 2026-07-20  
**Branch:** `phase-03-audit-hardening`  
**Hardening verdict:** **READY FOR RE-AUDIT** (do not create `phase-03-audited-pass` until independent re-audit)

---

## 1. Baseline and evidence commits

| Field | Value |
|-------|-------|
| Phase 2 audited baseline | `phase-02-audited-pass` @ `8930b3259cc076e1c308eefb24cb69f8a79bd08e` |
| Phase 3 implementation tip (pre-audit) | `982651a7237ae3b1b2ec76a7d41269adf42c24a4` |
| Audit evidence commit | `7a140dc` — `docs: record Phase 3 independent audit FAIL` |
| Prior audit | [`phase-03-audit.md`](./phase-03-audit.md) — **FAIL** (B-01, B-02, B-03) |

Scope constraint honored: no Phase 4 classification/facts/chronology/billing interpretation/LLM/drafting/export. No audited-pass tag.

---

## 2. B-01 — Retriable OCR init

### Root cause

Sticky `_init_attempted` + `_init_error` permanently poisoned the adapter until process restart.

### Design

Explicit module-private states in [`adapter.py`](../../backend/app/services/ocr/adapter.py):

```text
uninitialized → initializing → ready
                    ↓
              retry_wait (bounded cooldown)
                    ↓
              initializing (fresh attempt)
ready | initializing | retry_wait → shutting_down (lifespan)
```

- One in-flight init; waiters share success or `OcrUnavailableError`
- Failure leaves `_engine is None`, enters `retry_wait` for `ocr_init_retry_cooldown_ms` (default 2000)
- Success publishes engine only after full construct; `init_count` exact
- Lifespan calls `shutdown_adapter()` → `shutting_down`, clear engine, wake waiters
- Health remains import-based (`ocr_enabled`); does not call `ensure_engine`

### Tests

[`test_ocr_adapter.py`](../../backend/tests/unit/test_ocr_adapter.py): fail→success same process; shared waiter failure; cooldown retry; no sticky poison; shutdown cleanup; lock release invariants.

---

## 3. B-02 — Safe DELETE during process

### Root cause

Registry pop + `rmtree` while process thread still wrote workspace → Windows lock → HTTP 500 `session_cleanup_failed` (audit: 7/20 races).

### Design

1. Under lock: idempotent 204 if gone; else tombstone (`DELETED` / `deleting`), `generation += 1`, per-session `cancel_event`
2. Outside lock: `wait_until_idle(session_id)` drain
3. Idempotent `delete_workspace_tree` (missing = success; bounded PermissionError retry)
4. Drop registry; soft-fail residual FS races (no 500)

Write barriers in [`process/service.py`](../../backend/app/services/process/service.py): before workspace mkdir/write, thumbnail save, and OCR commit — re-check session exists, not deleting, generation matches, cancel not set. Late OCR results cannot commit.

### Tests

| Suite | Result |
|-------|--------|
| Barrier DELETE during normalize | 204; no orphan tree |
| Barrier DELETE before OCR commit | 204; discard |
| Double DELETE idempotent | 204 × 2 |
| Stress 100 controlled iterations | **100 × 204**; **0 × 500**; zero orphans |

---

## 4. B-03 — Under-detection gate + retry + geometry

### Root cause

High mean confidence + sparse tokens still yielded `ocr_usable`; coverage never demoted outcome; retry score was confidence-dominated. Audit police page 4: 6 tokens, `dark_pixel_fraction ≈ 0.335`, marked usable.

### Design

Multi-signal gate in [`ocr_quality.py`](../../backend/app/services/extraction/ocr_quality.py): under-detection only when **ink-rich** AND ≥2 of coverage floor / token floor / coverage-to-ink ratio / band concentration. Dark pixels alone never fail a page.

**Publish policy:** after best attempt, if still under-detected → do **not** mark usable; flag `insufficient_coverage`; issue `extraction.insufficient_ocr_coverage` (amber); **suppress** tokens/spans; `ocr_status=failed` (FE Retry works). No fabricated text.

Retry: under-detection triggers the single bounded retry; `score_pass_for_retry_choice` rebalanced so coverage/completeness can beat mean-confidence-alone.

Geometry (N-03): deskew `forward_affine` recorded; inverted into OCR polygons before normalize so highlights stay on canonical page.

FE: under-detection messaging; Retry on `insufficient_coverage` / `failed`.

### Provisional knobs (`0.1-provisional`)

`ocr_min_ink_for_coverage_check`, `ocr_min_token_coverage`, `ocr_min_coverage_to_ink_ratio`, `ocr_min_tokens_ink_rich`, `ocr_ink_binarize_threshold`, `ocr_under_detection_triggers_retry` — contracts + `03-ocr-thresholds.md`.

### Police page 4 probe (aliases/aggregates only)

| Field | Value |
|-------|-------|
| route | `ocr` |
| outcome | `ocr_failed` |
| under_detection | **true** |
| quality_flags | `insufficient_coverage` |
| ocr_status | `failed` |
| published_tokens | **0** |
| mean conf (pre-suppress) | ~0.95 |
| coverage | ~0.008 |
| dark_pixel_fraction | ~0.335 |
| retried | true |

Not marked `ocr_usable`. Tokens suppressed from usable APIs.

---

## 5. Reference package aggregates (safe aliases)

| Alias | native | ocr_routed | ocr_ok | warn | fail | tokens |
|-------|--------|------------|--------|------|------|--------|
| ecw_medical | 24/24 | 0 | — | — | — | 0 |
| ecw_billing | 0 | 1 | 1 | 1 | 0 | 136 |
| police (first 4) | 3 | 1 | 0 | 0 | 1 | 0 |
| insurer | 1 | 0 | — | — | — | — |
| long_medical (sample 6) | 6 | 0 | — | — | — | — |

---

## 6. Verification

| Gate | Result |
|------|--------|
| `node scripts/check-all.mjs` | **PASS** |
| Backend pytest | **164** passed |
| Frontend vitest | **9** passed |
| Contract drift | OK |
| Lockfile | unchanged on sync (no new production deps) |
| Light RSS (police page 4 probe) | ~73 MB → ~662 MB (OCR model load; investigate only if material growth vs prior tip) |

Preserved: OCR import boundary AST; single-worker OCR; PDFium lock order; eCW medical native; billing OCR + warning path.

---

## 7. Deliverables

| Artifact | Purpose |
|----------|---------|
| Evidence commit `7a140dc` | Failed audit report |
| This hardening commit | B-01 / B-02 / B-03 + tests + contracts |
| [`phase-03-hardening.md`](./phase-03-hardening.md) | This report — **READY FOR RE-AUDIT** |

---

## 8. Stop condition

**Stop.** Request a fresh independent re-audit of this tip.  
Do **not** create `phase-03-audited-pass`. Do **not** start Phase 4.
