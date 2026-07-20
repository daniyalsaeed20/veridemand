"""Build private human-review packages for selected pages."""

from __future__ import annotations

import json
import shutil
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CORPUS = ROOT / "tmp" / "extraction-remediation" / "acceptance-corpus"
FORENSIC_PAGES = ROOT / "tmp" / "extraction-forensic-investigation" / "pages"
REVIEW = ROOT / "tmp" / "extraction-remediation" / "acceptance-review"
EXAMPLE = ROOT / "docs" / "example"

PREFILL = "UNVERIFIED MACHINE PREFILL"


def _load_manifest() -> dict:
    path = CORPUS / "corpus_manifest.json"
    if not path.is_file():
        raise SystemExit("Run build_corpus_manifest.py first")
    return json.loads(path.read_text(encoding="utf-8"))


def _copy_if(src: Path, dest: Path) -> bool:
    if src.is_file():
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dest)
        return True
    return False


def _annotation_template(page: dict, *, reconstructed: str, native_words: list) -> dict:
    return {
        "page_id": page["page_id"],
        "safe_alias": page["safe_alias"],
        "page_number": page["page_number"],
        "annotation_status": "machine_prefill",
        "prefill_label": PREFILL,
        "expected_transcript": reconstructed,
        "expected_reading_order": [],
        "expected_critical_fields": [],
        "expected_boxes": [],
        "unreadable_regions": [],
        "reviewer": "",
        "review_date": "",
        "notes": "",
        "questions": {
            "text_matches_visible_page": None,
            "words_missing": None,
            "extra_words_present": None,
            "reading_order_correct": None,
            "boxes_enclose_correct_words": None,
            "native_text_layer_trustworthy": None,
            "fresh_ocr_required": None,
            "page_unreadable": None,
            "critical_values_exact": None,
        },
        "native_words_prefill": native_words,
        "warning": "Machine output is UNVERIFIED MACHINE PREFILL — not human ground truth",
    }


def build_html_index(pages: list[dict]) -> str:
    rows = []
    for p in pages:
        rows.append(
            "<tr>"
            f"<td>{p['page_id']}</td>"
            f"<td>{p['safe_alias']}</td>"
            f"<td>{p['page_number']}</td>"
            f"<td><a href='{p['page_id']}/annotation.json'>annotation</a></td>"
            f"<td><a href='{p['page_id']}/page_render.png'>render</a></td>"
            "</tr>"
        )
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8"/>
  <title>Extraction Acceptance Review (Private)</title>
  <style>
    body {{ font-family: Georgia, serif; margin: 2rem; background: #f7f5f1; color: #1a1a1a; }}
    h1 {{ font-size: 1.6rem; }}
    .banner {{ background: #fff3cd; border: 1px solid #e0c36c; padding: 0.75rem 1rem; margin-bottom: 1.5rem; }}
    table {{ border-collapse: collapse; width: 100%; background: #fff; }}
    th, td {{ border: 1px solid #ccc; padding: 0.4rem 0.6rem; text-align: left; }}
    th {{ background: #eee; }}
  </style>
</head>
<body>
  <h1>Extraction Acceptance Review</h1>
  <div class="banner">
    Technical extraction review only — not law-firm fact review.
    Prefills are <strong>{PREFILL}</strong>. Do not treat as gold.
  </div>
  <p>Answer per page (see annotation.json questions): text match, missing/extra words,
  reading order, boxes, native trustworthiness, fresh OCR need, unreadable, critical exactness.</p>
  <table>
    <thead><tr><th>Page ID</th><th>Alias</th><th>Page</th><th>Annotation</th><th>Render</th></tr></thead>
    <tbody>
      {''.join(rows)}
    </tbody>
  </table>
  <h2>Appendix</h2>
  <p>Full technical metadata lives beside each page (native_words.json, source dumps when copied from forensic).</p>
</body>
</html>
"""


def build() -> int:
    REVIEW.mkdir(parents=True, exist_ok=True)
    manifest = _load_manifest()
    built = 0
    for page in manifest.get("selected_pages") or []:
        pid = page["page_id"]
        dest = REVIEW / pid
        dest.mkdir(parents=True, exist_ok=True)

        forensic = FORENSIC_PAGES / pid
        reconstructed = ""
        native_words: list = []
        meta = {
            "page_id": pid,
            "safe_alias": page.get("safe_alias"),
            "page_number": page.get("page_number"),
            "selection_reason": page.get("selection_reason"),
            "built_at": datetime.now(timezone.utc).isoformat(),
            "prefill_label": PREFILL,
        }

        if forensic.is_dir():
            _copy_if(forensic / "page_render.png", dest / "page_render.png")
            _copy_if(forensic / "overlay_token_boxes.png", dest / "overlay_token_boxes.png")
            _copy_if(forensic / "overlay_token_order.png", dest / "overlay_token_order.png")
            _copy_if(forensic / "overlay_span_boundaries.png", dest / "overlay_span_boundaries.png")
            _copy_if(forensic / "reconstructed_text.txt", dest / "reconstructed_text.txt")
            _copy_if(forensic / "reading_order.txt", dest / "reading_order.txt")
            _copy_if(forensic / "native_words.json", dest / "native_words.json")
            _copy_if(forensic / "source_tokens.json", dest / "source_tokens.json")
            _copy_if(forensic / "source_spans.json", dest / "source_spans.json")
            _copy_if(forensic / "page_meta.json", dest / "page_meta.json")
            rt = dest / "reconstructed_text.txt"
            if rt.is_file():
                reconstructed = rt.read_text(encoding="utf-8", errors="replace")
            nw = dest / "native_words.json"
            if nw.is_file():
                try:
                    native_words = json.loads(nw.read_text(encoding="utf-8"))
                except json.JSONDecodeError:
                    native_words = []
            if (forensic / "page_meta.json").is_file():
                meta["forensic_meta"] = json.loads(
                    (forensic / "page_meta.json").read_text(encoding="utf-8")
                )
        else:
            (dest / "reconstructed_text.txt").write_text(
                f"{PREFILL}\n(no forensic dump for this page yet)\n",
                encoding="utf-8",
            )
            reconstructed = ""

        ann = _annotation_template(page, reconstructed=reconstructed, native_words=native_words)
        # Seed user-confirmed anchors as editable fields without claiming page linkage complete
        if page.get("safe_alias") in {"ecw_medical", "long_medical", "insurer", "existing_demand"}:
            ann["expected_critical_fields"].append(
                {
                    "field_id": "client_name",
                    "field_type": "person_name",
                    "expected": "Mayel Amini",
                    "status": "USER_CONFIRMED_ANCHOR",
                    "page_link_confirmed": False,
                }
            )
        if page.get("safe_alias") in {"existing_demand", "long_medical"}:
            ann["expected_critical_fields"].append(
                {
                    "field_id": "law_firm",
                    "field_type": "law_firm_name",
                    "expected": "The Jackman Law Firm, PLLC",
                    "status": "USER_CONFIRMED_ANCHOR",
                    "page_link_confirmed": False,
                }
            )

        (dest / "page_metadata.json").write_text(json.dumps(meta, indent=2) + "\n", encoding="utf-8")
        (dest / "annotation.json").write_text(json.dumps(ann, indent=2) + "\n", encoding="utf-8")
        (dest / "technical_appendix.json").write_text(
            json.dumps(
                {
                    "note": "Technical metadata appendix",
                    "has_forensic_dump": forensic.is_dir(),
                    "files": sorted(p.name for p in dest.iterdir() if p.is_file()),
                },
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        built += 1

    (REVIEW / "index.html").write_text(
        build_html_index(manifest.get("selected_pages") or []),
        encoding="utf-8",
    )
    (REVIEW / "README.txt").write_text(
        "PRIVATE extraction acceptance review pack.\n"
        f"Open index.html. Prefills are {PREFILL}.\n"
        "Do not commit this directory.\n",
        encoding="utf-8",
    )
    return built


if __name__ == "__main__":
    n = build()
    print(f"review pack pages: {n} -> {REVIEW}")
