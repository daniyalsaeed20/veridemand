"""
Isolated billing ledger parser spike.
Uses positioned words, header-based columns, Decimal money, CPT extraction,
and total reconciliation. Does not invent claimed specials.

Note: the eCW ledger sample has a heavily corrupted native text layer ((cid:N)
glyphs). This spike documents what can be recovered from native words vs what
must create review issues / OCR routing.
"""
from __future__ import annotations

import json
import re
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from pathlib import Path

import pdfplumber

ROOT = Path(__file__).resolve().parents[2]
LEDGER = ROOT / "docs" / "example" / "AMINI_MAYEL_20260706_eCW Billing Ledger.pdf"
OUT = Path(__file__).resolve().parent / "out"
OUT.mkdir(parents=True, exist_ok=True)

MONEY_RE = re.compile(r"^\(?-?\$?\d{1,3}(?:,\d{3})*(?:\.\d{2})\)?$")
CODE6_RE = re.compile(r"^\d{6}$")  # observed on this ledger (not classic 5-digit CPT)
CPT5_RE = re.compile(r"^\d{5}$")
CID_RE = re.compile(r"\(cid:\d+\)")


def parse_money(raw: str) -> Decimal | None:
    s = raw.strip()
    neg = False
    if s.startswith("(") and s.endswith(")"):
        neg = True
        s = s[1:-1]
    s = s.replace("$", "").replace(",", "").strip()
    if not s or s in {"-", "—"}:
        return None
    try:
        val = Decimal(s).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        return -val if neg else val
    except InvalidOperation:
        return None


def y_overlap(a, b) -> bool:
    return not (a["bottom"] < b["top"] or b["bottom"] < a["top"])


def group_rows(words: list[dict], y_tol: float = 3.0) -> list[list[dict]]:
    if not words:
        return []
    ordered = sorted(words, key=lambda w: (round(w["top"] / y_tol) * y_tol, w["x0"]))
    rows: list[list[dict]] = []
    current: list[dict] = [ordered[0]]
    current_y = ordered[0]["top"]
    for w in ordered[1:]:
        if abs(w["top"] - current_y) <= y_tol or y_overlap(w, current[0]):
            current.append(w)
            current_y = min(current_y, w["top"])
        else:
            rows.append(sorted(current, key=lambda x: x["x0"]))
            current = [w]
            current_y = w["top"]
    rows.append(sorted(current, key=lambda x: x["x0"]))
    return rows


def detect_headers(rows: list[list[dict]]) -> tuple[dict[str, float], int]:
    header_aliases = {
        "date": ["date", "dos", "service", "servicedate"],
        "cpt": ["cpt", "code", "proc", "procedure"],
        "description": ["description", "desc", "service"],
        "charge": ["charge", "charges", "amount", "billed", "fee"],
        "payment": ["payment", "paid", "pay"],
        "adjustment": ["adjustment", "adj", "adjust"],
        "balance": ["balance", "bal", "owed", "total"],
        "provider": ["provider", "rendering"],
        "patient": ["patient"],
        "transaction": ["transaction", "patienttransaction"],
    }
    best = {}
    best_idx = -1
    best_hits = 0
    for i, row in enumerate(rows[:30]):
        hits = {}
        for w in row:
            wt = w["text"].lower().strip(":").strip()
            if CID_RE.search(wt):
                continue
            for key, aliases in header_aliases.items():
                if any(a == wt or a in wt for a in aliases):
                    hits[key] = (w["x0"] + w["x1"]) / 2
        if len(hits) > best_hits:
            best_hits = len(hits)
            best = hits
            best_idx = i
    return best, best_idx


def main() -> None:
    report = {
        "spike": "billing",
        "source": LEDGER.name,
        "correctly_reconstructed": [],
        "layout_specific_rules_needed": [],
        "should_create_review_issues": [],
        "cannot_yet_determine": [],
        "native_diagnostics": {},
        "money_tokens": [],
        "code_tokens": [],
        "reconciliation": {},
        "warnings": [],
    }
    if not LEDGER.exists():
        report["warnings"].append("ledger_missing")
        (OUT / "metrics.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
        return

    with pdfplumber.open(str(LEDGER)) as pdf:
        report["page_count"] = len(pdf.pages)
        page = pdf.pages[0]
        words = page.extract_words() or []
        text = page.extract_text() or ""

    cid_words = sum(1 for w in words if CID_RE.search(w["text"]))
    report["native_diagnostics"] = {
        "page_size": [float(page.width), float(page.height)],
        "word_count": len(words),
        "cid_encoded_words": cid_words,
        "cid_ratio": round(cid_words / max(len(words), 1), 3),
        "title_tokens_readable": [
            w["text"] for w in words if w["text"] in {"PatientTransaction", "Report"} or "AMINI" in w["text"].upper()
        ][:10],
    }

    if report["native_diagnostics"]["cid_ratio"] > 0.3:
        report["should_create_review_issues"].append(
            "Broken native text layer (high (cid:N) ratio) — route page to OCR (extraction.broken_text_layer) "
            "and do not trust native column text for CPT/description."
        )
        report["layout_specific_rules_needed"].append(
            "eCW PatientTransaction landscape ledger: native encoding unusable for most headers; "
            "OCR or alternate export format required before reliable row grouping."
        )

    # Recover what we can from intact tokens (money / numeric codes)
    money_hits = []
    code_hits = []
    for w in words:
        t = w["text"]
        if CID_RE.search(t):
            continue
        m = parse_money(t)
        if m is not None and ("$" in t or "." in t):
            money_hits.append(
                {
                    "raw": t,
                    "decimal": str(m),
                    "x0": round(w["x0"], 1),
                    "top": round(w["top"], 1),
                }
            )
        if CODE6_RE.match(t) or CPT5_RE.match(t):
            code_hits.append({"raw": t, "x0": round(w["x0"], 1), "top": round(w["top"], 1)})

    report["money_tokens"] = money_hits
    report["code_tokens"] = code_hits

    # Row grouping still runs to show structure exists
    rows = group_rows(words)
    headers, header_idx = detect_headers(rows)
    report["detected_headers"] = headers
    report["header_row_index"] = header_idx
    report["row_group_count"] = len(rows)

    # Heuristic: money tokens near right margin are likely charge/balance columns
    if money_hits:
        rightish = [m for m in money_hits if m["x0"] > 650]
        report["correctly_reconstructed"].append(
            f"Recovered {len(money_hits)} currency-like tokens via Decimal parsing "
            f"({len(rightish)} near right margin, likely amount column)."
        )
        amounts = [Decimal(m["decimal"]) for m in money_hits]
        # Separate obvious totals: larger absolute values / parentheses adjustments
        positives = [a for a in amounts if a > 0]
        negatives = [a for a in amounts if a < 0]
        report["reconciliation"] = {
            "money_token_count": len(amounts),
            "sum_all_money_tokens": str(sum(amounts, Decimal("0.00"))),
            "sum_positive_tokens": str(sum(positives, Decimal("0.00"))),
            "sum_negative_tokens": str(sum(negatives, Decimal("0.00"))),
            "unique_amounts": sorted({str(a) for a in amounts}),
            "note": (
                "Summing all money tokens is NOT a verified ledger total — tokens include "
                "line charges and printed subtotals/balances. Requires OCR + header map."
            ),
        }
        # Check for duplicate-looking subtotal figures
        from collections import Counter

        c = Counter(str(a) for a in amounts)
        dupes = {k: v for k, v in c.items() if v > 1}
        if dupes:
            report["layout_specific_rules_needed"].append(
                f"Duplicate amount values seen {dupes} — likely line + subtotal echo; "
                "dedupe by row type before reconciliation."
            )
    else:
        report["cannot_yet_determine"].append("No currency tokens recoverable from native layer.")

    if code_hits:
        report["correctly_reconstructed"].append(
            f"Recovered {len(code_hits)} left-column numeric codes "
            f"({sorted({c['raw'] for c in code_hits})}); pattern is 6-digit on this sample, "
            "not classic 5-digit CPT — treat as layout-specific code field pending OCR/label confirmation."
        )
        report["layout_specific_rules_needed"].append(
            "Do not assume 5-digit CPT; this eCW export exposes 6-digit transaction/procedure codes in native layer."
        )
        report["cannot_yet_determine"].append(
            "Whether left-column codes are CPT, charge codes, or internal IDs — labels are (cid:)-garbled."
        )
    else:
        report["cannot_yet_determine"].append("No CPT/procedure codes recovered from native words.")

    if len(headers) < 3:
        report["should_create_review_issues"].append(
            "Header-based column assignment failed under native extraction — create billing.layout_uncertain "
            "review issue and require OCR or manual mapping."
        )

    # Attempt naive reconciliation story
    if money_hits:
        # Last large positive often a balance/total candidate — not asserted as truth
        sorted_by_y = sorted(money_hits, key=lambda m: m["top"])
        report["cannot_yet_determine"].append(
            f"Printed total/balance identity unknown. Last money token by Y is "
            f"{sorted_by_y[-1]['raw']} at top={sorted_by_y[-1]['top']} — needs label from OCR."
        )

    report["correctly_reconstructed"].append(
        "Positioned-word geometry is available (landscape 792x612); row grouping produced "
        f"{len(rows)} provisional rows."
    )
    report["should_create_review_issues"].append(
        "FR-BIL-04: legally claimed specials must not be inferred — queue user confirmation."
    )
    report["cannot_yet_determine"].append(
        "Authoritative provider totals for gold eval remain unset (see gold-readiness.md)."
    )
    report["layout_specific_rules_needed"].append(
        "After OCR, map columns by detected header x-centers; merge wrapped description rows by Y proximity."
    )

    # Sample readable non-cid snippet for report (no excess PII)
    readable = [w["text"] for w in words if not CID_RE.search(w["text"])][:40]
    report["readable_native_sample"] = readable

    (OUT / "metrics.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps({k: report[k] for k in report if k not in {"readable_native_sample"}}, indent=2))


if __name__ == "__main__":
    main()
