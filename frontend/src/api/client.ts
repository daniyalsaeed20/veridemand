import {
  DocumentSchema,
  DocumentUploadBatchSchema,
  ErrorEnvelopeSchema,
  type Document,
  type DocumentUploadBatch,
  type ErrorEnvelope,
  type UploadRejection,
} from "../schemas/documents";
import { CaseSessionSchema, type CaseSession } from "../schemas/session";
import { HealthResponseSchema, type HealthResponse } from "../schemas/health";
import {
  DocumentPageSchema,
  ProcessEventSchema,
  SourceSpanSchema,
  SourceTokenSchema,
  type DocumentPage,
  type ProcessEvent,
  type SourceSpan,
  type SourceToken,
} from "../schemas/viewer";

const baseUrl =
  (import.meta.env.VITE_API_BASE_URL as string | undefined) ?? "http://127.0.0.1:8000";

export class ApiError extends Error {
  readonly status: number;
  readonly envelope: ErrorEnvelope | null;

  constructor(status: number, message: string, envelope: ErrorEnvelope | null = null) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.envelope = envelope;
  }
}

async function parseError(response: Response): Promise<ApiError> {
  try {
    const json: unknown = await response.json();
    const parsed = ErrorEnvelopeSchema.safeParse(json);
    if (parsed.success) {
      return new ApiError(response.status, parsed.data.message, parsed.data);
    }
  } catch {
    /* fall through */
  }
  return new ApiError(response.status, `Request failed (${response.status})`);
}

function parseArray<T>(
  json: unknown,
  schema: { safeParse: (v: unknown) => { success: boolean; data?: T } },
  label: string,
): T[] {
  if (!Array.isArray(json)) {
    throw new Error(`${label} response failed contract validation`);
  }
  const out: T[] = [];
  for (const item of json) {
    const parsed = schema.safeParse(item);
    if (!parsed.success || parsed.data === undefined) {
      throw new Error(`${label} response failed contract validation`);
    }
    out.push(parsed.data);
  }
  return out;
}

export async function fetchHealth(): Promise<HealthResponse> {
  const response = await fetch(`${baseUrl}/api/v1/health`);
  if (!response.ok) {
    throw await parseError(response);
  }
  const json: unknown = await response.json();
  const parsed = HealthResponseSchema.safeParse(json);
  if (!parsed.success) {
    throw new Error("Backend health response failed contract validation");
  }
  return parsed.data;
}

export async function createSession(): Promise<CaseSession> {
  const response = await fetch(`${baseUrl}/api/v1/sessions`, { method: "POST" });
  if (!response.ok) {
    throw await parseError(response);
  }
  const json: unknown = await response.json();
  const parsed = CaseSessionSchema.safeParse(json);
  if (!parsed.success) {
    throw new Error("Session response failed contract validation");
  }
  return parsed.data;
}

export async function getSession(sessionId: string): Promise<CaseSession> {
  const response = await fetch(`${baseUrl}/api/v1/sessions/${encodeURIComponent(sessionId)}`);
  if (!response.ok) {
    throw await parseError(response);
  }
  const json: unknown = await response.json();
  const parsed = CaseSessionSchema.safeParse(json);
  if (!parsed.success) {
    throw new Error("Session response failed contract validation");
  }
  return parsed.data;
}

export async function deleteSession(sessionId: string): Promise<void> {
  const response = await fetch(`${baseUrl}/api/v1/sessions/${encodeURIComponent(sessionId)}`, {
    method: "DELETE",
  });
  if (!response.ok && response.status !== 204) {
    throw await parseError(response);
  }
}

export async function uploadDocuments(
  sessionId: string,
  files: File[],
): Promise<DocumentUploadBatch> {
  const form = new FormData();
  for (const file of files) {
    form.append("files", file, file.name);
  }
  const response = await fetch(
    `${baseUrl}/api/v1/sessions/${encodeURIComponent(sessionId)}/documents`,
    { method: "POST", body: form },
  );
  if (!response.ok) {
    throw await parseError(response);
  }
  const json: unknown = await response.json();
  const parsed = DocumentUploadBatchSchema.safeParse(json);
  if (!parsed.success) {
    throw new Error("Upload response failed contract validation");
  }
  return parsed.data;
}

export async function listDocuments(sessionId: string): Promise<Document[]> {
  const response = await fetch(
    `${baseUrl}/api/v1/sessions/${encodeURIComponent(sessionId)}/documents`,
  );
  if (!response.ok) {
    throw await parseError(response);
  }
  const json: unknown = await response.json();
  return parseArray(json, DocumentSchema, "Document list");
}

export async function deleteDocument(sessionId: string, documentId: string): Promise<void> {
  const response = await fetch(
    `${baseUrl}/api/v1/sessions/${encodeURIComponent(sessionId)}/documents/${encodeURIComponent(documentId)}`,
    { method: "DELETE" },
  );
  if (!response.ok && response.status !== 204) {
    throw await parseError(response);
  }
}

export type DocumentPatch = {
  classification?: string;
  display_name?: string;
  sequence_index?: number;
  exclude_from_drafting?: boolean;
  treat_as_secondary_evidence?: boolean;
  confirm_classification?: boolean;
  confirm_authority_review?: boolean;
  revert_to_proposed?: boolean;
};

export async function patchDocument(
  sessionId: string,
  documentId: string,
  patch: DocumentPatch,
): Promise<Document> {
  const response = await fetch(
    `${baseUrl}/api/v1/sessions/${encodeURIComponent(sessionId)}/documents/${encodeURIComponent(documentId)}`,
    {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(patch),
    },
  );
  if (!response.ok) {
    throw await parseError(response);
  }
  const json: unknown = await response.json();
  const parsed = DocumentSchema.safeParse(json);
  if (!parsed.success) {
    throw new Error("Document patch response failed contract validation");
  }
  return parsed.data;
}

export async function updateDocumentSequence(
  sessionId: string,
  documentIds: string[],
): Promise<Document[]> {
  const response = await fetch(
    `${baseUrl}/api/v1/sessions/${encodeURIComponent(sessionId)}/documents/sequence`,
    {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ document_ids: documentIds }),
    },
  );
  if (!response.ok) {
    throw await parseError(response);
  }
  const json: unknown = await response.json();
  return parseArray(json, DocumentSchema, "Document sequence");
}

export async function startProcess(sessionId: string): Promise<ProcessEvent[]> {
  const response = await fetch(
    `${baseUrl}/api/v1/sessions/${encodeURIComponent(sessionId)}/process`,
    { method: "POST" },
  );
  if (!response.ok) {
    throw await parseError(response);
  }
  const json: unknown = await response.json();
  return parseArray(json, ProcessEventSchema, "Process");
}

export async function waitForProcess(
  sessionId: string,
  options?: { timeoutMs?: number; pollMs?: number },
): Promise<ProcessEvent[]> {
  const timeoutMs = options?.timeoutMs ?? 600_000;
  const pollMs = options?.pollMs ?? 400;
  const started = await startProcess(sessionId);
  let after = started.length > 0 ? Math.max(...started.map((e) => e.sequence)) : -1;
  const collected = [...started];
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    if (
      collected.some((e) =>
        ["process.completed", "process.failed", "process.cancelled"].includes(e.event),
      )
    ) {
      return collected;
    }
    await new Promise((r) => setTimeout(r, pollMs));
    const batch = await listEvents(sessionId, after);
    if (batch.length > 0) {
      collected.push(...batch);
      after = batch[batch.length - 1]!.sequence;
    }
  }
  throw new Error("Timed out waiting for document processing");
}

export async function listEvents(sessionId: string, after = -1): Promise<ProcessEvent[]> {
  const response = await fetch(
    `${baseUrl}/api/v1/sessions/${encodeURIComponent(sessionId)}/events?after=${after}`,
  );
  if (!response.ok) {
    throw await parseError(response);
  }
  const json: unknown = await response.json();
  return parseArray(json, ProcessEventSchema, "Events");
}

export async function listIssues(sessionId: string): Promise<unknown[]> {
  const response = await fetch(
    `${baseUrl}/api/v1/sessions/${encodeURIComponent(sessionId)}/issues`,
  );
  if (!response.ok) {
    throw await parseError(response);
  }
  const json: unknown = await response.json();
  if (!Array.isArray(json)) {
    throw new Error("Issues response failed contract validation");
  }
  return json;
}

export async function retryOcrPage(
  sessionId: string,
  documentId: string,
  pageNumber: number,
): Promise<DocumentPage> {
  const response = await fetch(
    `${baseUrl}/api/v1/sessions/${encodeURIComponent(sessionId)}/documents/${encodeURIComponent(documentId)}/pages/${pageNumber}/ocr/retry`,
    { method: "POST" },
  );
  if (!response.ok) {
    throw await parseError(response);
  }
  const json: unknown = await response.json();
  const parsed = DocumentPageSchema.safeParse(json);
  if (!parsed.success) {
    throw new Error("Retry OCR response failed contract validation");
  }
  return parsed.data;
}

export async function listPages(sessionId: string, documentId: string): Promise<DocumentPage[]> {
  const response = await fetch(
    `${baseUrl}/api/v1/sessions/${encodeURIComponent(sessionId)}/documents/${encodeURIComponent(documentId)}/pages`,
  );
  if (!response.ok) {
    throw await parseError(response);
  }
  const json: unknown = await response.json();
  return parseArray(json, DocumentPageSchema, "Pages");
}

export async function listSpans(
  sessionId: string,
  documentId: string,
  pageNumber: number,
): Promise<SourceSpan[]> {
  const response = await fetch(
    `${baseUrl}/api/v1/sessions/${encodeURIComponent(sessionId)}/documents/${encodeURIComponent(documentId)}/pages/${pageNumber}/spans`,
  );
  if (!response.ok) {
    throw await parseError(response);
  }
  const json: unknown = await response.json();
  return parseArray(json, SourceSpanSchema, "Spans");
}

export async function listTokens(
  sessionId: string,
  documentId: string,
  pageNumber: number,
): Promise<SourceToken[]> {
  const response = await fetch(
    `${baseUrl}/api/v1/sessions/${encodeURIComponent(sessionId)}/documents/${encodeURIComponent(documentId)}/pages/${pageNumber}/tokens`,
  );
  if (!response.ok) {
    throw await parseError(response);
  }
  const json: unknown = await response.json();
  return parseArray(json, SourceTokenSchema, "Tokens");
}

export function canonicalViewUrl(sessionId: string, documentId: string): string {
  return `${baseUrl}/api/v1/sessions/${encodeURIComponent(sessionId)}/documents/${encodeURIComponent(documentId)}/view`;
}

export function thumbnailUrl(sessionId: string, documentId: string, pageNumber: number): string {
  return `${baseUrl}/api/v1/sessions/${encodeURIComponent(sessionId)}/documents/${encodeURIComponent(documentId)}/thumbnails/${pageNumber}`;
}

export type {
  CaseSession,
  Document,
  DocumentPage,
  DocumentUploadBatch,
  ErrorEnvelope,
  HealthResponse,
  ProcessEvent,
  SourceSpan,
  SourceToken,
  UploadRejection,
};
