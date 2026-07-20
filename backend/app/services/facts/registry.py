"""Parser registry — catalog-aligned deterministic parsers."""

from __future__ import annotations

from app.models.enums import DocumentClassification
from app.services.facts.types import ParserSpec

_ALL = frozenset(DocumentClassification)

PARSER_SPECS: tuple[ParserSpec, ...] = (
    # Identity
    ParserSpec(
        "det.client.name.v1",
        "client.name",
        ("Patient", "Claimant", "Plaintiff", "Name of Injured", "Injured Party"),
        frozenset(
            {
                DocumentClassification.MEDICAL_RECORD,
                DocumentClassification.POLICE_REPORT,
                DocumentClassification.BILL_LEDGER,
            }
        ),
        "critical",
        "name",
        negative_cues=("Attorney", "Adjuster", "Provider", "Insured Driver"),
    ),
    ParserSpec(
        "det.client.dob.v1",
        "client.dob",
        ("DOB", "Date of Birth", "Birth Date"),
        frozenset({DocumentClassification.MEDICAL_RECORD, DocumentClassification.POLICE_REPORT}),
        "critical",
        "date",
    ),
    ParserSpec(
        "det.client.phone.v1",
        "client.phone",
        ("Patient Phone", "Claimant Phone", "Home Phone", "Mobile", "Cell Phone"),
        frozenset({DocumentClassification.MEDICAL_RECORD, DocumentClassification.POLICE_REPORT}),
        "normal",
        "phone",
        negative_cues=("Attorney", "Law Firm", "Office Phone", "Provider Phone"),
    ),
    ParserSpec(
        "det.client.email.v1",
        "client.email",
        ("Patient Email", "Claimant Email", "Email Address"),
        frozenset({DocumentClassification.MEDICAL_RECORD}),
        "normal",
        "email",
        negative_cues=("Attorney", "Law Firm"),
    ),
    ParserSpec(
        "det.client.address.v1",
        "client.address",
        ("Patient Address", "Residence", "Address"),
        frozenset({DocumentClassification.MEDICAL_RECORD}),
        "normal",
        "text",
    ),
    ParserSpec(
        "det.client.pronouns.v1",
        "client.pronouns",
        ("Sex", "Gender"),
        frozenset({DocumentClassification.MEDICAL_RECORD}),
        "critical",
        "pronoun",
    ),
    ParserSpec(
        "det.attorney.name.v1",
        "attorney.name",
        ("Attorney", "Counsel", "Law Firm"),
        frozenset(
            {
                DocumentClassification.EXISTING_DEMAND,
                DocumentClassification.TEMPLATE,
                DocumentClassification.OTHER,
                DocumentClassification.INSURER_CORRESPONDENCE,
            }
        ),
        "normal",
        "name",
    ),
    ParserSpec(
        "det.attorney.phone.v1",
        "attorney.phone",
        ("Attorney Phone", "Office Phone", "Firm Phone"),
        frozenset(
            {
                DocumentClassification.EXISTING_DEMAND,
                DocumentClassification.INSURER_CORRESPONDENCE,
                DocumentClassification.OTHER,
            }
        ),
        "normal",
        "phone",
    ),
    ParserSpec(
        "det.attorney.email.v1",
        "attorney.email",
        ("Attorney Email", "Counsel Email"),
        frozenset(
            {
                DocumentClassification.EXISTING_DEMAND,
                DocumentClassification.INSURER_CORRESPONDENCE,
            }
        ),
        "normal",
        "email",
    ),
    # Claim / insurer
    ParserSpec(
        "det.insurer.name.v1",
        "insurer.name",
        ("Insurer", "Insurance Company", "Carrier", "Claims Department"),
        frozenset(
            {
                DocumentClassification.INSURER_CORRESPONDENCE,
                DocumentClassification.POLICE_REPORT,
            }
        ),
        "critical",
        "name",
    ),
    ParserSpec(
        "det.insured.name.v1",
        "insured.name",
        ("Insured", "Your Insured", "Named Insured"),
        frozenset(
            {
                DocumentClassification.POLICE_REPORT,
                DocumentClassification.INSURER_CORRESPONDENCE,
            }
        ),
        "critical",
        "name",
        negative_cues=("Claimant", "Patient", "Plaintiff"),
    ),
    ParserSpec(
        "det.adjuster.name.v1",
        "adjuster.name",
        ("Adjuster", "Claim Representative"),
        frozenset({DocumentClassification.INSURER_CORRESPONDENCE}),
        "normal",
        "name",
    ),
    ParserSpec(
        "det.claim.number.v1",
        "claim.number",
        ("Claim No", "Claim Number", "Claim #", "Claim No."),
        frozenset(
            {
                DocumentClassification.INSURER_CORRESPONDENCE,
                DocumentClassification.BILL_LEDGER,
                DocumentClassification.POLICE_REPORT,
            }
        ),
        "critical",
        "identifier",
        negative_cues=("Policy", "Citation", "Report No", "Example Claim"),
    ),
    ParserSpec(
        "det.policy.number.v1",
        "policy.number",
        ("Policy No", "Policy Number", "Policy #", "Policy No."),
        frozenset({DocumentClassification.INSURER_CORRESPONDENCE}),
        "critical",
        "identifier",
        negative_cues=("Claim", "Citation"),
    ),
    # Collision
    ParserSpec(
        "det.collision.date.v1",
        "collision.date",
        ("Date of Loss", "DOL", "Date of Collision", "Accident Date", "Date of Accident"),
        frozenset(
            {
                DocumentClassification.POLICE_REPORT,
                DocumentClassification.MEDICAL_RECORD,
                DocumentClassification.INSURER_CORRESPONDENCE,
            }
        ),
        "critical",
        "date",
        negative_cues=("Date of Service", "DOB", "Birth", "Printed", "Visit Date"),
    ),
    ParserSpec(
        "det.collision.time.v1",
        "collision.time",
        ("Time of Loss", "Time of Accident", "Time of Collision"),
        frozenset({DocumentClassification.POLICE_REPORT}),
        "normal",
        "time",
    ),
    ParserSpec(
        "det.collision.report_number.v1",
        "collision.report_number",
        ("Report No", "Report Number", "Case No", "Incident No", "Report #"),
        frozenset({DocumentClassification.POLICE_REPORT}),
        "critical",
        "identifier",
        negative_cues=("Claim No", "Policy", "Citation"),
    ),
    ParserSpec(
        "det.collision.location.v1",
        "collision.location",
        ("Location", "Place of Accident", "Intersection", "Accident Location"),
        frozenset({DocumentClassification.POLICE_REPORT}),
        "critical",
        "text",
    ),
    ParserSpec(
        "det.liability.citation.v1",
        "liability.citation",
        ("Citation", "Citation No", "Infraction", "Citation #"),
        frozenset({DocumentClassification.POLICE_REPORT}),
        "normal",
        "identifier",
        negative_cues=("Claim", "Policy"),
    ),
    # Medical
    ParserSpec(
        "det.medical.provider.v1",
        "medical.provider",
        ("Provider", "Rendering Provider", "Facility", "Clinic"),
        frozenset({DocumentClassification.MEDICAL_RECORD, DocumentClassification.BILL_LEDGER}),
        "normal",
        "name",
        negative_cues=("Attorney", "Insurer"),
    ),
    ParserSpec(
        "det.medical.provider_phone.v1",
        "medical.provider_phone",
        ("Provider Phone", "Clinic Phone", "Facility Phone"),
        frozenset({DocumentClassification.MEDICAL_RECORD, DocumentClassification.BILL_LEDGER}),
        "normal",
        "phone",
    ),
    ParserSpec(
        "det.medical.visit_date.v1",
        "medical.visit_date",
        ("DOS", "Date of Service", "Visit Date", "Encounter Date"),
        frozenset({DocumentClassification.MEDICAL_RECORD, DocumentClassification.BILL_LEDGER}),
        "normal",
        "date",
        negative_cues=("Date of Loss", "DOB", "Accident"),
    ),
    ParserSpec(
        "det.medical.diagnosis.icd.v1",
        "medical.diagnosis",
        ("Diagnosis", "ICD", "ICD-10", "Dx", "ICD10"),
        frozenset({DocumentClassification.MEDICAL_RECORD, DocumentClassification.BILL_LEDGER}),
        "critical",
        "icd10",
    ),
    ParserSpec(
        "det.imaging.study_date.v1",
        "imaging.study_date",
        ("Study Date", "Exam Date", "MRI Date"),
        frozenset(
            {
                DocumentClassification.MEDICAL_RECORD,
                DocumentClassification.IMAGING_REPORT,
            }
        ),
        "normal",
        "date",
    ),
    ParserSpec(
        "det.imaging.modality.v1",
        "imaging.modality",
        ("Modality",),
        frozenset(
            {
                DocumentClassification.MEDICAL_RECORD,
                DocumentClassification.IMAGING_REPORT,
            }
        ),
        "normal",
        "text",
    ),
    # Billing
    ParserSpec(
        "det.damages.charge.v1",
        "damages.charge",
        ("Charge", "Amount Billed", "Billed Amount"),
        frozenset({DocumentClassification.BILL_LEDGER}),
        "normal",
        "money",
        negative_cues=("Settlement", "Demand Amount", "Authorized"),
    ),
    ParserSpec(
        "det.damages.payment.v1",
        "damages.payment",
        ("Payment", "Paid", "Ins Pay"),
        frozenset({DocumentClassification.BILL_LEDGER}),
        "normal",
        "money",
    ),
    ParserSpec(
        "det.damages.adjustment.v1",
        "damages.adjustment",
        ("Adjustment", "Adj", "Write-off", "Write off"),
        frozenset({DocumentClassification.BILL_LEDGER}),
        "normal",
        "money",
    ),
    ParserSpec(
        "det.damages.balance.v1",
        "damages.balance",
        ("Balance", "Amount Due", "Patient Bal"),
        frozenset({DocumentClassification.BILL_LEDGER}),
        "normal",
        "money",
    ),
    ParserSpec(
        "det.billing.cpt.v1",
        "billing.cpt",
        ("CPT", "Procedure Code"),
        frozenset({DocumentClassification.BILL_LEDGER}),
        "normal",
        "cpt",
    ),
    ParserSpec(
        "det.damages.specials_claimed.v1",
        "damages.specials_claimed",
        ("Medical Specials", "Total Specials", "Specials Claimed"),
        frozenset(
            {
                DocumentClassification.BILL_LEDGER,
                DocumentClassification.EXISTING_DEMAND,
            }
        ),
        "critical",
        "money",
    ),
    ParserSpec(
        "det.damages.lien.v1",
        "damages.lien",
        ("Lien", "Lien Amount"),
        frozenset({DocumentClassification.LIEN, DocumentClassification.BILL_LEDGER}),
        "normal",
        "money",
    ),
    # Correspondence
    ParserSpec(
        "det.corr.offer_deadline.v1",
        "correspondence.offer_deadline",
        ("Offer expires", "Respond by", "Deadline"),
        frozenset({DocumentClassification.INSURER_CORRESPONDENCE}),
        "critical",
        "date",
    ),
    ParserSpec(
        "det.corr.response_deadline.v1",
        "correspondence.response_deadline",
        ("Please respond by", "Due Date", "Response Due"),
        frozenset({DocumentClassification.INSURER_CORRESPONDENCE}),
        "normal",
        "date",
    ),
)


def specs_for_classification(
    classification: DocumentClassification | None,
) -> list[ParserSpec]:
    if classification is None:
        return list(PARSER_SPECS)
    matched = [s for s in PARSER_SPECS if classification in s.doc_classes]
    # Label-driven fallback when no class-matched parsers exist
    return matched if matched else list(PARSER_SPECS)
