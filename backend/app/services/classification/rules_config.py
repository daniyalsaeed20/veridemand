"""Configuration-driven classification rule dictionaries and weights."""

from __future__ import annotations

from dataclasses import dataclass

from app.models.enums import DocumentClassification


@dataclass(frozen=True)
class PhraseRule:
    rule_id: str
    classification: DocumentClassification
    phrases: tuple[str, ...]
    weight: float
    source: str  # filename | content | heading


# Filename token rules (lower weight — cannot alone decide)
FILENAME_RULES: tuple[PhraseRule, ...] = (
    PhraseRule(
        "fn_police",
        DocumentClassification.POLICE_REPORT,
        ("police", "collision", "incident"),
        0.35,
        "filename",
    ),
    PhraseRule(
        "fn_insurer",
        DocumentClassification.INSURER_CORRESPONDENCE,
        ("insurance", "insurer", "carrier", "adjuster"),
        0.35,
        "filename",
    ),
    PhraseRule(
        "fn_medical",
        DocumentClassification.MEDICAL_RECORD,
        ("medical", "records", "emr", "ecw", "clinic", "chiro"),
        0.35,
        "filename",
    ),
    PhraseRule(
        "fn_billing",
        DocumentClassification.BILL_LEDGER,
        ("billing", "ledger", "invoice", "cpt", "bill"),
        0.40,
        "filename",
    ),
    PhraseRule(
        "fn_imaging",
        DocumentClassification.IMAGING_REPORT,
        ("mri", "xray", "x-ray", "radiology", "imaging"),
        0.35,
        "filename",
    ),
    PhraseRule("fn_lien", DocumentClassification.LIEN, ("lien",), 0.45, "filename"),
    PhraseRule(
        "fn_wage",
        DocumentClassification.WAGE_LOSS,
        ("wage", "payroll", "employment"),
        0.40,
        "filename",
    ),
    PhraseRule(
        "fn_photo",
        DocumentClassification.PHOTOGRAPHS,
        ("photo", "photograph", "image", "jpg", "jpeg", "png"),
        0.35,
        "filename",
    ),
    PhraseRule("fn_demand", DocumentClassification.EXISTING_DEMAND, ("demand",), 0.30, "filename"),
    PhraseRule("fn_template", DocumentClassification.TEMPLATE, ("template",), 0.40, "filename"),
)

# Strong content/heading rules (higher weight)
CONTENT_RULES: tuple[PhraseRule, ...] = (
    PhraseRule(
        "ct_police",
        DocumentClassification.POLICE_REPORT,
        (
            "police report",
            "collision report",
            "traffic collision",
            "incident report",
            "reporting officer",
            "case number",
            "washington state patrol",
        ),
        0.85,
        "content",
    ),
    PhraseRule(
        "ct_insurer",
        DocumentClassification.INSURER_CORRESPONDENCE,
        (
            "claims department",
            "claim number",
            "policy number",
            "dear insured",
            "insurance company",
            "coverage determination",
            "reservation of rights",
        ),
        0.80,
        "content",
    ),
    PhraseRule(
        "ct_medical",
        DocumentClassification.MEDICAL_RECORD,
        (
            "patient information",
            "medical records",
            "chief complaint",
            "assessment",
            "plan of care",
            "history of present illness",
            "physical examination",
            "progress note",
            "clinical summary",
            "ecw",
            "electronic medical record",
        ),
        0.85,
        "content",
    ),
    PhraseRule(
        "ct_imaging",
        DocumentClassification.IMAGING_REPORT,
        (
            "radiology report",
            "mri report",
            "x-ray report",
            "impression:",
            "findings:",
            "magnetic resonance",
            "computed tomography",
        ),
        0.80,
        "content",
    ),
    PhraseRule(
        "ct_billing",
        DocumentClassification.BILL_LEDGER,
        (
            "billing ledger",
            "cpt code",
            "procedure code",
            "charges",
            "amount due",
            "patient balance",
            "ledger",
            "total charges",
            "icd-10",
            "icd10",
        ),
        0.85,
        "content",
    ),
    PhraseRule(
        "ct_lien",
        DocumentClassification.LIEN,
        (
            "notice of lien",
            "lien amount",
            "lien holder",
            "medical lien",
        ),
        0.85,
        "content",
    ),
    PhraseRule(
        "ct_wage",
        DocumentClassification.WAGE_LOSS,
        (
            "wage loss",
            "lost wages",
            "employer verification",
            "pay stub",
            "hours missed",
            "rate of pay",
        ),
        0.80,
        "content",
    ),
    PhraseRule(
        "ct_demand",
        DocumentClassification.EXISTING_DEMAND,
        (
            "demand for settlement",
            "demand letter",
            "settlement demand",
            "we demand",
            "policy limits demand",
            "[settlement amount",
            "tbd]",
            "re: your insured",
            "demand package",
        ),
        0.90,
        "content",
    ),
    PhraseRule(
        "ct_template",
        DocumentClassification.TEMPLATE,
        (
            "demand template",
            "sample demand",
            "template instructions",
            "[client name]",
            "[insert",
            "firm template",
        ),
        0.85,
        "content",
    ),
)

# Weak keywords — insufficient alone
WEAK_KEYWORDS: frozenset[str] = frozenset(
    {
        "claim",
        "medical",
        "invoice",
        "report",
        "document",
        "letter",
        "records",
    }
)

# Precedence tier order (lower index = higher priority when resolving ties)
PRECEDENCE_TIERS: tuple[tuple[DocumentClassification, ...], ...] = (
    (DocumentClassification.EXISTING_DEMAND, DocumentClassification.TEMPLATE),
    (DocumentClassification.POLICE_REPORT, DocumentClassification.INSURER_CORRESPONDENCE),
    (DocumentClassification.MEDICAL_RECORD, DocumentClassification.IMAGING_REPORT),
    (DocumentClassification.BILL_LEDGER, DocumentClassification.LIEN),
    (DocumentClassification.WAGE_LOSS,),
    (DocumentClassification.PHOTOGRAPHS,),
    (DocumentClassification.OTHER,),
)

# Sequence category rank (lower = earlier in proposed order)
SEQUENCE_RANK: dict[DocumentClassification, int] = {
    DocumentClassification.POLICE_REPORT: 0,
    DocumentClassification.INSURER_CORRESPONDENCE: 1,
    DocumentClassification.MEDICAL_RECORD: 2,
    DocumentClassification.IMAGING_REPORT: 3,
    DocumentClassification.BILL_LEDGER: 4,
    DocumentClassification.LIEN: 5,
    DocumentClassification.WAGE_LOSS: 6,
    DocumentClassification.PHOTOGRAPHS: 7,
    DocumentClassification.OTHER: 8,
    DocumentClassification.EXISTING_DEMAND: 9,
    DocumentClassification.TEMPLATE: 10,
}

# Minimum score gap to avoid ambiguity between top two candidates
AMBIGUITY_SCORE_GAP = 0.12

# Filename-only cap when content contradicts
FILENAME_ONLY_CAP = 0.45
