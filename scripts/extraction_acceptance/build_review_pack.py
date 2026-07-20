"""Private review pack + machine prefill builder for the annotation app."""

from __future__ import annotations

import json
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from extraction_acceptance.review_app.annotation_store import new_annotation

CORPUS = ROOT / "tmp" / "extraction-remediation" / "acceptance-corpus"
FORENSIC_PAGES = ROOT / "tmp" / "extraction-forensic-investigation" / "pages"
REVIEW = ROOT / "tmp" / "extraction-remediation" / "acceptance-review"
BACKEND = ROOT / "backend"

PREFILL_LABEL = "UNVERIFIED MACHINE OUTPUT"


def _load_manifest() -> dict:
    path = CORPUS / "corpus_manifest.json"
    if not path.is_file():
        raise SystemExit("Run build_corpus_manifest.py first")
    return json.loads(path.read_text(encoding="utf-8"))


def _doc_path(doc: dict) -> Path | None:
    rel = doc.get("canonical_relpath")
    if not rel:
        return None
    p = ROOT / rel
    return p if p.is_file() else None


def _render_page(pdf_path: Path, page_number: int, dest_png: Path, *, scale: float = 2.0) -> bool:
    try:
        import pypdfium2 as pdfium
    except ImportError:
        return False
    try:
        doc = pdfium.PdfDocument(str(pdf_path))
        page = doc[page_number - 1]
        bitmap = page.render(scale=scale)
        pil = bitmap.to_pil()
        dest_png.parent.mkdir(parents=True, exist_ok=True)
        pil.save(dest_png)
        return True
    except Exception:  # noqa: BLE001
        return False


def _native_extract(pdf_path: Path, page_number: int) -> dict:
    if str(BACKEND) not in sys.path:
        sys.path.insert(0, str(BACKEND))
    from app.models.app_settings import AppSettings
    from app.services.extraction.native import extract_native_page

    result = extract_native_page(
        pdf_path,
        document_id="doc_01JREVIEW0000000000000001",
        page_number=page_number,
        settings=AppSettings(),
    )
    words = []
    for i, tok in enumerate(result.tokens):
        poly = [[float(p[0]), float(p[1])] for p in (tok.polygon or [])]
        words.append(
            {
                "id": tok.id if hasattr(tok, "id") else f"W{i}",
                "text": tok.text,
                "reading_order": i,
                "polygon": poly,
                "confidence": getattr(tok, "confidence", None),
                "layer": "native_pdf_text",
                "granularity": "word",
            }
        )
    transcript = " ".join(w["text"] for w in words)
    # Prefer line breaks from spans if present
    lines = []
    for i, span in enumerate(result.spans or []):
        lines.append(
            {
                "id": getattr(span, "id", f"L{i}"),
                "text": span.text,
                "reading_order": i,
                "polygon": [[float(p[0]), float(p[1])] for p in (span.polygons[0] if span.polygons else [])]
                if span.polygons
                else None,
                "layer": "native_pdf_text",
                "granularity": "line",
            }
        )
    if lines:
        transcript = "\n".join(ln["text"] for ln in lines)
    return {
        "route": result.page.route.value,
        "rotation": result.rotation,
        "words": words,
        "lines": lines,
        "transcript": transcript,
        "char_count": result.diagnostics.char_count if result.diagnostics else None,
        "warnings": list(result.diagnostics.warnings) if result.diagnostics else [],
        "engine": {"name": "pdfplumber", "version": "bundled", "configuration": {"path": "native"}},
    }


def _copy_forensic(page_id: str, dest: Path) -> dict:
    """Map forensic folder names loosely."""
    candidates = [FORENSIC_PAGES / page_id]
    # legacy short aliases
    mapping = {
        "amini_police_p1": "police_p1",
        "amini_ecw_billing_p1": "ecw_billing_p1",
        "amini_ecw_medical_p15": "ecw_medical_p15",
        "amini_ecw_medical_p16": "ecw_medical_p16",
        "amini_ecw_medical_p17": "ecw_medical_p17",
        "amini_ecw_medical_p18": "ecw_medical_p18",
        "amini_ecw_medical_p19": "ecw_medical_p19",
        "amini_ecw_medical_p20": "ecw_medical_p20",
        "amini_ecw_medical_p21": "ecw_medical_p21",
        "amini_ecw_medical_p22": "ecw_medical_p22",
        "amini_ecw_medical_p23": "ecw_medical_p23",
        "amini_ecw_medical_p24": "ecw_medical_p24",
        "amini_insurer_p1": "insurer_p1",
        "amini_long_medical_p1": "long_medical_p1",
        "amini_long_medical_p2": "long_medical_p2",
        "amini_long_medical_p19": "long_medical_p19",
        "amini_long_medical_p36": "long_medical_p36",
        "amini_existing_demand_p1": "existing_demand_p1",
    }
    if page_id in mapping:
        candidates.insert(0, FORENSIC_PAGES / mapping[page_id])
    for src in candidates:
        if not src.is_dir():
            continue
        for name in (
            "page_render.png",
            "native_words.json",
            "source_tokens.json",
            "source_spans.json",
            "reconstructed_text.txt",
            "reading_order.txt",
            "overlay_token_boxes.png",
            "page_meta.json",
        ):
            f = src / name
            if f.is_file():
                shutil.copy2(f, dest / name)
        return {"forensic_dir": src.name, "copied": True}
    return {"copied": False}


def _maybe_ocr(pdf_path: Path, page_number: int, native: dict, dest: Path) -> dict | None:
    if native.get("route") != "ocr":
        # Still check forensic tokens
        tok_path = dest / "source_tokens.json"
        if tok_path.is_file():
            try:
                toks = json.loads(tok_path.read_text(encoding="utf-8"))
                return {
                    "source": "forensic_cache",
                    "token_count": len(toks) if isinstance(toks, list) else 0,
                    "label": PREFILL_LABEL,
                }
            except json.JSONDecodeError:
                return None
        return None
    tok_path = dest / "source_tokens.json"
    if tok_path.is_file():
        try:
            toks = json.loads(tok_path.read_text(encoding="utf-8"))
            lines = []
            if isinstance(toks, list):
                for i, t in enumerate(toks):
                    if isinstance(t, dict):
                        lines.append(
                            {
                                "id": t.get("id") or f"O{i}",
                                "text": t.get("text") or "",
                                "reading_order": i,
                                "polygon": t.get("polygon"),
                                "confidence": t.get("confidence"),
                                "layer": "fresh_ocr",
                                "granularity": "line",
                            }
                        )
            transcript = "\n".join(ln["text"] for ln in lines)
            (dest / "ocr_lines.json").write_text(
                json.dumps({"label": PREFILL_LABEL, "lines": lines}, indent=2) + "\n",
                encoding="utf-8",
            )
            (dest / "ocr_transcript.txt").write_text(transcript, encoding="utf-8")
            return {
                "source": "forensic_cache",
                "token_count": len(lines),
                "transcript": transcript,
                "label": PREFILL_LABEL,
                "engine": {"name": "paddleocr", "version": "2.7.3", "configuration": {"cached": True}},
            }
        except json.JSONDecodeError:
            pass
    # Live OCR (optional, may be slow)
    try:
        if str(BACKEND) not in sys.path:
            sys.path.insert(0, str(BACKEND))
        from app.models.app_settings import AppSettings
        from app.services.extraction.native import extract_native_page
        from app.services.extraction.ocr_page import extract_ocr_page
        from app.services.ocr import ocr_capability_enabled

        if not ocr_capability_enabled():
            return {"source": "skipped", "reason": "ocr_not_enabled", "label": PREFILL_LABEL}
        settings = AppSettings()
        native_res = extract_native_page(
            pdf_path,
            document_id="doc_01JREVIEW0000000000000001",
            page_number=page_number,
            settings=settings,
        )
        ocr = extract_ocr_page(
            pdf_path,
            document_id="doc_01JREVIEW0000000000000001",
            page=native_res.page,
            settings=settings,
            page_rotation=native_res.rotation,
        )
        lines = []
        for i, tok in enumerate(ocr.tokens):
            lines.append(
                {
                    "id": getattr(tok, "id", f"O{i}"),
                    "text": tok.text,
                    "reading_order": i,
                    "polygon": [[float(p[0]), float(p[1])] for p in (tok.polygon or [])],
                    "confidence": getattr(tok, "confidence", None),
                    "layer": "fresh_ocr",
                    "granularity": "line",
                }
            )
        transcript = "\n".join(ln["text"] for ln in lines)
        (dest / "ocr_lines.json").write_text(
            json.dumps({"label": PREFILL_LABEL, "lines": lines}, indent=2) + "\n",
            encoding="utf-8",
        )
        (dest / "ocr_transcript.txt").write_text(transcript, encoding="utf-8")
        return {
            "source": "live_paddleocr",
            "token_count": len(lines),
            "transcript": transcript,
            "label": PREFILL_LABEL,
            "engine": {
                "name": "paddleocr",
                "version": "2.7.3",
                "configuration": {"use_gpu": False},
            },
        }
    except Exception as exc:  # noqa: BLE001
        return {"source": "error", "reason": type(exc).__name__, "label": PREFILL_LABEL}


def build(*, run_ocr: bool = True) -> int:
    REVIEW.mkdir(parents=True, exist_ok=True)
    pages_root = REVIEW / "pages"
    pages_root.mkdir(parents=True, exist_ok=True)
    (REVIEW / "backups").mkdir(parents=True, exist_ok=True)

    manifest = _load_manifest()
    docs_by_alias = {d["doc_alias"]: d for d in manifest.get("documents") or []}
    built = 0

    for page in manifest.get("selected_pages") or []:
        page_id = page["page_id"]
        dest = pages_root / page_id
        dest.mkdir(parents=True, exist_ok=True)

        doc = docs_by_alias.get(page["doc_alias"]) or {}
        pdf = _doc_path(doc) if doc else None
        pn = int(page.get("page_number") or 1)

        forensic_info = _copy_forensic(page_id, dest)

        native = {
            "route": None,
            "words": [],
            "lines": [],
            "transcript": "",
            "warnings": [],
        }
        if pdf and pdf.suffix.lower() == ".pdf":
            try:
                native = _native_extract(pdf, pn)
                (dest / "native_words.json").write_text(
                    json.dumps(
                        {"label": PREFILL_LABEL, "words": native["words"], "engine": native["engine"]},
                        indent=2,
                    )
                    + "\n",
                    encoding="utf-8",
                )
                (dest / "native_lines.json").write_text(
                    json.dumps({"label": PREFILL_LABEL, "lines": native["lines"]}, indent=2) + "\n",
                    encoding="utf-8",
                )
                (dest / "native_transcript.txt").write_text(native["transcript"], encoding="utf-8")
            except Exception as exc:  # noqa: BLE001
                native["warnings"] = [type(exc).__name__]

            if not (dest / "page_render.png").is_file():
                _render_page(pdf, pn, dest / "page_render.png")

        ocr_info = None
        if run_ocr and pdf and pdf.suffix.lower() == ".pdf":
            ocr_info = _maybe_ocr(pdf, pn, native, dest)

        # Choose display machine transcript: OCR if routed and available, else native
        machine_transcript = native.get("transcript") or ""
        if ocr_info and ocr_info.get("transcript"):
            if native.get("route") == "ocr" or not machine_transcript.strip():
                machine_transcript = ocr_info["transcript"]
        if not machine_transcript.strip() and (dest / "reconstructed_text.txt").is_file():
            machine_transcript = (dest / "reconstructed_text.txt").read_text(
                encoding="utf-8", errors="replace"
            )

        # Reading order from lines
        order_src = native.get("lines") or [
            {"id": w["id"], "text": w["text"], "reading_order": w["reading_order"]}
            for w in native.get("words") or []
        ]
        if ocr_info and (dest / "ocr_lines.json").is_file():
            ocr_lines = json.loads((dest / "ocr_lines.json").read_text(encoding="utf-8"))
            if native.get("route") == "ocr" and ocr_lines.get("lines"):
                order_src = ocr_lines["lines"]

        prefill = {
            "label": PREFILL_LABEL,
            "page_id": page_id,
            "built_at": datetime.now(timezone.utc).isoformat(),
            "native": {
                "route": native.get("route"),
                "transcript": native.get("transcript") or "",
                "word_count": len(native.get("words") or []),
                "line_count": len(native.get("lines") or []),
                "warnings": native.get("warnings") or [],
                "engine": native.get("engine"),
            },
            "ocr": ocr_info,
            "forensic": forensic_info,
            "layers_separate": True,
            "note": "Do not treat as human ground truth",
        }
        (dest / "machine_prefill.json").write_text(
            json.dumps(prefill, indent=2) + "\n", encoding="utf-8"
        )

        ann_path = dest / "annotation.json"
        if ann_path.is_file():
            # Do not overwrite human work; refresh machine_transcript only if still prefill
            existing = json.loads(ann_path.read_text(encoding="utf-8"))
            if existing.get("annotation_status") in {"machine_prefill", None}:
                existing["machine_transcript"] = machine_transcript
                existing["machine_reading_order"] = [
                    {"id": x.get("id"), "text": x.get("text"), "reading_order": x.get("reading_order")}
                    for x in order_src
                ]
                if not existing.get("critical_fields") and page.get("critical_anchors"):
                    existing["critical_fields"] = [
                        {
                            **a,
                            "machine_reading": "",
                            "match_status": "unresolved",
                            "status": a.get("status") or "USER_CONFIRMED_ANCHOR",
                        }
                        for a in page.get("critical_anchors") or []
                    ]
                ann_path.write_text(json.dumps(existing, indent=2) + "\n", encoding="utf-8")
        else:
            crit = []
            for a in page.get("critical_anchors") or []:
                crit.append(
                    {
                        **a,
                        "machine_reading": "",
                        "status": a.get("status") or "USER_CONFIRMED_ANCHOR",
                        "match_status": "unresolved",
                    }
                )
            # Seed machine reading for badge corrupt candidate when present in transcript
            for c in crit:
                if c.get("corrupt_embedded_candidate") and c["corrupt_embedded_candidate"] in (
                    native.get("transcript") or ""
                ):
                    c["machine_reading"] = c["corrupt_embedded_candidate"]
                    c["layer"] = "embedded_ocr"
            ann = new_annotation(
                page_id=page_id,
                case_alias=str(page.get("case_alias") or ""),
                doc_alias=str(page.get("doc_alias") or ""),
                page_number=pn,
                machine_transcript=machine_transcript,
                critical_fields=crit,
                challenges=list(page.get("challenges") or []),
            )
            ann["machine_reading_order"] = [
                {"id": x.get("id"), "text": x.get("text"), "reading_order": x.get("reading_order")}
                for x in order_src
            ]
            ann_path.write_text(json.dumps(ann, indent=2) + "\n", encoding="utf-8")

        (dest / "page_meta.json").write_text(
            json.dumps(
                {
                    "page_id": page_id,
                    "case_alias": page.get("case_alias"),
                    "doc_alias": page.get("doc_alias"),
                    "page_number": pn,
                    "challenges": page.get("challenges") or [],
                    "selection_reason": page.get("selection_reason"),
                    "has_render": (dest / "page_render.png").is_file(),
                    "has_native": bool(native.get("words")),
                    "has_ocr": bool(ocr_info and ocr_info.get("token_count")),
                    "route": native.get("route"),
                },
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        built += 1

    # Private launcher copy
    launcher = REVIEW / "start_review.cmd"
    launcher.write_text(
        "@echo off\r\n"
        "setlocal\r\n"
        "cd /d \"%~dp0\\..\\..\\..\"\r\n"
        "echo Starting extraction review on http://127.0.0.1:8765/\r\n"
        "backend\\.venv\\Scripts\\python.exe scripts\\extraction_acceptance\\start_review_server.py\r\n",
        encoding="utf-8",
    )
    (REVIEW / "README.txt").write_text(
        "PRIVATE extraction acceptance review pack.\n"
        "Launch via start_review.cmd or:\n"
        "  backend\\.venv\\Scripts\\python.exe scripts\\extraction_acceptance\\start_review_server.py\n"
        "Open http://127.0.0.1:8765/ — do not use file:///\n"
        "Prefills are UNVERIFIED MACHINE OUTPUT.\n",
        encoding="utf-8",
    )
    return built


if __name__ == "__main__":
    n = build(run_ocr=True)
    print(f"review pack pages: {n} -> {REVIEW}")
