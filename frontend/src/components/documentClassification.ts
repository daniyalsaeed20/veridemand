import { patchDocument, updateDocumentSequence, type Document } from "../api/client";

export const CLASSIFICATION_OPTIONS = [
  { value: "police_report", label: "Police report" },
  { value: "insurer_correspondence", label: "Insurer correspondence" },
  { value: "medical_record", label: "Medical record" },
  { value: "imaging_report", label: "Imaging report" },
  { value: "bill_ledger", label: "Bill / ledger" },
  { value: "lien", label: "Lien" },
  { value: "wage_loss", label: "Wage loss" },
  { value: "photographs", label: "Photographs" },
  { value: "existing_demand", label: "Existing demand" },
  { value: "template", label: "Firm template" },
  { value: "other", label: "Other / unknown" },
] as const;

export function classificationLabel(value: string | null | undefined): string {
  if (!value) return "Unclassified";
  return CLASSIFICATION_OPTIONS.find((o) => o.value === value)?.label ?? value;
}

export function sortDocuments(docs: Document[]): Document[] {
  return [...docs].sort((a, b) => {
    const ai = a.sequence_index ?? 9999;
    const bi = b.sequence_index ?? 9999;
    if (ai !== bi) return ai - bi;
    return a.display_name.localeCompare(b.display_name);
  });
}

export function isViewable(doc: Document): boolean {
  return doc.status === "extracted" || doc.status === "classified";
}

export async function saveClassification(
  sessionId: string,
  documentId: string,
  classification: string,
): Promise<Document> {
  return patchDocument(sessionId, documentId, { classification });
}

export async function confirmClassification(
  sessionId: string,
  documentId: string,
): Promise<Document> {
  return patchDocument(sessionId, documentId, { confirm_classification: true });
}

export async function toggleExclude(
  sessionId: string,
  documentId: string,
  exclude: boolean,
): Promise<Document> {
  return patchDocument(sessionId, documentId, { exclude_from_drafting: exclude });
}

export async function toggleSecondaryEvidence(
  sessionId: string,
  documentId: string,
  enabled: boolean,
): Promise<Document> {
  return patchDocument(sessionId, documentId, { treat_as_secondary_evidence: enabled });
}

export async function reorderDocuments(
  sessionId: string,
  documentIds: string[],
): Promise<Document[]> {
  return updateDocumentSequence(sessionId, documentIds);
}
