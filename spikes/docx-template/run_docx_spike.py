"""
Isolated docxtpl template spike.
Inspects a Jackman-style demand for style cues, builds a Jinja template,
and renders a dummy multi-page demand. Not evidence authority.
"""
from __future__ import annotations

import json
from pathlib import Path

from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_LINE_SPACING
from docx.oxml.ns import qn
from docx.shared import Inches, Pt, Twips
from docxtpl import DocxTemplate

ROOT = Path(__file__).resolve().parents[2]
EXAMPLE = ROOT / "docs" / "example"
OUT = Path(__file__).resolve().parent / "out"
OUT.mkdir(parents=True, exist_ok=True)

# Actual on-disk name has double space
AMINI_DEMAND = EXAMPLE / "Demand Mayel  Amini Final.docx"
FALLBACK_DEMAND = EXAMPLE / "Demand - Morris, Sandra.docx"


def inspect_style(path: Path) -> dict:
    info = {
        "path": path.name,
        "exists": path.exists(),
        "paragraph_count": 0,
        "table_count": 0,
        "sections": 0,
        "fonts_seen": [],
        "has_header": False,
        "has_footer": False,
        "sample_styles": [],
    }
    if not path.exists():
        return info
    doc = Document(str(path))
    info["paragraph_count"] = len(doc.paragraphs)
    info["table_count"] = len(doc.tables)
    info["sections"] = len(doc.sections)
    fonts = set()
    for p in doc.paragraphs[:40]:
        for r in p.runs:
            if r.font.name:
                fonts.add(r.font.name)
        if p.text.strip():
            info["sample_styles"].append(
                {
                    "style": p.style.name if p.style else None,
                    "align": str(p.alignment) if p.alignment else None,
                    "text_len": len(p.text.strip()),
                }
            )
    for section in doc.sections:
        if section.header.paragraphs and any(p.text.strip() for p in section.header.paragraphs):
            info["has_header"] = True
        if section.footer.paragraphs and any(p.text.strip() for p in section.footer.paragraphs):
            info["has_footer"] = True
    info["fonts_seen"] = sorted(fonts)
    return info


def set_run_font(run, name: str = "Times New Roman", size: int = 12) -> None:
    run.font.name = name
    run._element.rPr.rFonts.set(qn("w:eastAsia"), name)
    run.font.size = Pt(size)


def build_template(path: Path) -> None:
    doc = Document()
    section = doc.sections[0]
    section.top_margin = Inches(1)
    section.bottom_margin = Inches(1)
    section.left_margin = Inches(1)
    section.right_margin = Inches(1)

    # Header
    header = section.header
    hp = header.paragraphs[0]
    hp.alignment = WD_ALIGN_PARAGRAPH.CENTER
    hr = hp.add_run("{{ firm_name }}")
    set_run_font(hr, size=14)
    hp2 = header.add_paragraph()
    hp2.alignment = WD_ALIGN_PARAGRAPH.CENTER
    set_run_font(hp2.add_run("{{ firm_address }}"), size=10)

    # Footer
    footer = section.footer
    fp = footer.paragraphs[0]
    fp.alignment = WD_ALIGN_PARAGRAPH.CENTER
    set_run_font(fp.add_run("Page "), size=9)
    # simple page marker text; Word page fields omitted for spike simplicity
    set_run_font(fp.add_run("{{ page_footer_note }}"), size=9)

    def add_para(text: str, bold: bool = False, size: int = 12, space_after: int = 8):
        p = doc.add_paragraph()
        p.paragraph_format.space_after = Pt(space_after)
        p.paragraph_format.line_spacing_rule = WD_LINE_SPACING.SINGLE
        run = p.add_run(text)
        set_run_font(run, size=size)
        run.bold = bold
        return p

    add_para("{{ letter_date }}")
    add_para("{{ recipient_name }}")
    add_para("{{ recipient_company }}")
    add_para("{{ recipient_address }}")
    add_para("")
    add_para("Re: {{ re_line }}", bold=True)
    add_para("Claim No.: {{ claim_number }}")
    add_para("Our Client: {{ client_name }}")
    add_para("Date of Loss: {{ date_of_loss }}")
    add_para("")
    add_para("Dear {{ salutation_name }}:")
    add_para("{{ intro_paragraph }}")

    # Treatment providers (repeated)
    add_para("TREATMENT BY PROVIDER", bold=True, size=12)
    # docxtpl loop markers as paragraphs
    add_para("{%p for provider in providers %}")
    add_para("{{ provider.name }}", bold=True)
    add_para("Dates of service: {{ provider.dos_range }}")
    add_para("{{ provider.narrative }}")
    add_para("{%p endfor %}")

    add_para("SPECIALS", bold=True)
    table = doc.add_table(rows=1, cols=3)
    table.style = "Table Grid"
    hdr = table.rows[0].cells
    hdr[0].text = "Provider"
    hdr[1].text = "Description"
    hdr[2].text = "Amount"
    # docxtpl row loop: add a row with placeholders
    row = table.add_row().cells
    row[0].text = "{%tr for item in specials %}"
    # Actually docxtpl uses {%tr for %} in first cell differently — use paragraphs after table via list
    # Simpler approach: build specials table cells with jinja in a second row template pattern
    doc._body._body.remove(table._tbl)

    # Rebuild specials with docxtpl-friendly single table
    add_para("(Specials table follows)")
    table = doc.add_table(rows=2, cols=3)
    table.style = "Table Grid"
    for i, label in enumerate(["Provider", "Description", "Amount"]):
        table.rows[0].cells[i].text = label
        for p in table.rows[0].cells[i].paragraphs:
            for r in p.runs:
                set_run_font(r, size=11)
                r.bold = True
    table.rows[1].cells[0].text = "{% for item in specials %}{{ item.provider }}"
    table.rows[1].cells[1].text = "{{ item.description }}"
    table.rows[1].cells[2].text = "{{ item.amount }}{% endfor %}"

    # Better: use docxtpl rich table via vertical merge alternative — keep list fallback
    add_para("{%p for item in specials %}")
    add_para("{{ item.provider }} — {{ item.description }}: {{ item.amount }}")
    add_para("{%p endfor %}")
    add_para("Total specials (subject to confirmation): {{ specials_total }}")

    add_para("SETTLEMENT PROPOSAL", bold=True)
    add_para("{{ settlement_paragraph }}")
    add_para("Demand amount: {{ demand_amount }}")

    add_para("CLOSING", bold=True)
    add_para("{{ closing_paragraph }}")
    add_para("")
    add_para("Very truly yours,")
    add_para("")
    add_para("{{ attorney_name }}")
    add_para("{{ firm_name }}")

    add_para("EXHIBITS", bold=True)
    add_para("{%p for exhibit in exhibits %}")
    add_para("{{ exhibit }}")
    add_para("{%p endfor %}")

    # Force multi-page filler via jinja
    add_para("{%p for block in filler_blocks %}")
    add_para("{{ block }}")
    add_para("{%p endfor %}")

    doc.save(str(path))


def render_dummy(template_path: Path, out_path: Path) -> dict:
    tpl = DocxTemplate(str(template_path))
    filler = []
    para = (
        "This placeholder narrative expands the demand body so Microsoft Word-compatible "
        "pagination, headers, and footers can be inspected across multiple pages. "
        "It is synthetic readiness content and is not case evidence. "
    )
    for i in range(1, 18):
        filler.append(f"Continuation paragraph {i}. " + para * 3)

    providers = [
        {
            "name": "Provider Alpha Clinic",
            "dos_range": "2026-04-01 to 2026-04-30",
            "narrative": "Synthetic treatment summary for template fidelity testing. " * 8,
        },
        {
            "name": "Provider Beta Imaging",
            "dos_range": "2026-05-02",
            "narrative": "Synthetic imaging summary for repeated-section testing. " * 8,
        },
        {
            "name": "Provider Gamma Chiropractic",
            "dos_range": "2026-05-10 to 2026-06-15",
            "narrative": "Synthetic chiropractic course description for multi-provider sections. " * 10,
        },
    ]
    specials = [
        {"provider": "Provider Alpha Clinic", "description": "Evaluation/management", "amount": "1,200.00"},
        {"provider": "Provider Beta Imaging", "description": "Imaging", "amount": "850.00"},
        {"provider": "Provider Gamma Chiropractic", "description": "Manipulative therapy", "amount": "2,400.00"},
    ]
    context = {
        "firm_name": "Jackman-Style Sample Firm (Template Spike)",
        "firm_address": "123 Demo Street, Suite 100, Sample City, ST 00000",
        "page_footer_note": "(spike footer — not a live matter)",
        "letter_date": "July 19, 2026",
        "recipient_name": "Claims Adjuster",
        "recipient_company": "Sample Insurance Company",
        "recipient_address": "1 Carrier Way, City, ST 00000",
        "re_line": "Our Client / Your Insured — Motor Vehicle Collision (DUMMY)",
        "claim_number": "DUMMY-CLAIM-000",
        "client_name": "Dummy Client",
        "date_of_loss": "2026-03-28",
        "salutation_name": "Adjuster",
        "intro_paragraph": (
            "This is a synthetic demand letter generated solely to evaluate docxtpl formatting "
            "fidelity for the VeriDemand prototype readiness spike."
        ),
        "providers": providers,
        "specials": specials,
        "specials_total": "4,450.00",
        "settlement_paragraph": (
            "Subject to attorney judgment and evidence approval, this spike inserts a settlement "
            "proposal section. No authorized demand amount is asserted as a verified fact."
        ),
        "demand_amount": "[SETTLEMENT AMOUNT - TBD]",
        "closing_paragraph": (
            "Please contact undersigned counsel upon review. This document is a formatting fixture."
        ),
        "attorney_name": "Sample Attorney, Esq.",
        "exhibits": [
            "Exhibit A — Police report (dummy)",
            "Exhibit B — Medical records (dummy)",
            "Exhibit C — Billing ledger (dummy)",
            "Exhibit D — Photographs (listed; may be missing in corpus)",
        ],
        "filler_blocks": filler,
    }
    tpl.render(context)
    tpl.save(str(out_path))

    # Post-render inspection
    rendered = Document(str(out_path))
    return {
        "output": out_path.name,
        "paragraphs": len(rendered.paragraphs),
        "tables": len(rendered.tables),
        "sections": len(rendered.sections),
        "header_text_sample": rendered.sections[0].header.paragraphs[0].text[:120]
        if rendered.sections
        else "",
        "footer_text_sample": rendered.sections[0].footer.paragraphs[0].text[:120]
        if rendered.sections
        else "",
        "approx_chars": sum(len(p.text) for p in rendered.paragraphs),
    }


def main() -> None:
    style_source = AMINI_DEMAND if AMINI_DEMAND.exists() else FALLBACK_DEMAND
    inspection = inspect_style(style_source)
    template_path = OUT / "jackman_like_demand_template.docx"
    rendered_path = OUT / "dummy_demand_rendered.docx"

    build_template(template_path)
    render_info = render_dummy(template_path, rendered_path)

    # Evaluate fidelity checklist (manual Word open still required)
    evaluation = {
        "headers": "Present via section header with firm name/address placeholders; verify in Word.",
        "footers": "Present with spike footer note; true PAGE fields not injected in this spike.",
        "tables": f"Rendered document contains {render_info['tables']} table(s); specials also listed as paragraphs for reliability.",
        "page_breaks": "Multi-page expected from filler_blocks (~17 long paragraphs); confirm pagination in Word/LibreOffice.",
        "fonts": "Template forces Times New Roman (common demand letter face); compare to style source fonts_seen.",
        "spacing": "Single spacing, 1-inch margins; not a pixel-perfect clone of firm letterhead art.",
        "repeated_sections": "providers and exhibits use {%p for %} loops; specials dual-path (table attempt + paragraph loop).",
        "limitations": [
            "Letterhead graphics/logos from firm DOCX were not copied (avoid embedding matter PII/branding binary complexity).",
            "Table row-level {%tr%} looping was not relied on as sole specials path due to docxtpl/table fragility.",
            "Open rendered DOCX in Microsoft Word to confirm WYSIWYG; python-docx cannot fully certify Word layout.",
        ],
    }

    report = {
        "spike": "docx-template",
        "style_source_inspection": inspection,
        "template": str(template_path.relative_to(ROOT)),
        "rendered": str(rendered_path.relative_to(ROOT)),
        "render_info": render_info,
        "evaluation": evaluation,
        "dummy_contains": [
            "header_and_re_block",
            "multiple_treatment_provider_sections",
            "specials_table_and_list",
            "settlement_proposal",
            "closing_and_signature",
            "exhibit_list",
            "multi_page_filler",
        ],
    }
    out_json = OUT / "metrics.json"
    out_json.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
