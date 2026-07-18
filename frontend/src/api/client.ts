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
  if (!Array.isArray(json)) {
    throw new Error("Document list response failed contract validation");
  }
  const docs: Document[] = [];
  for (const item of json) {
    const parsed = DocumentSchema.safeParse(item);
    if (!parsed.success) {
      throw new Error("Document list response failed contract validation");
    }
    docs.push(parsed.data);
  }
  return docs;
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

export type {
  CaseSession,
  Document,
  DocumentUploadBatch,
  ErrorEnvelope,
  HealthResponse,
  UploadRejection,
};
