/**
 * Document and upload-batch contracts — generated Zod + tightened wire validation.
 */
import { z } from "zod";
import { DocumentSchema as GeneratedDocument } from "./generated/Document";
import { DocumentUploadBatchSchema as GeneratedBatch } from "./generated/DocumentUploadBatch";
import { UploadRejectionSchema as GeneratedRejection } from "./generated/UploadRejection";

export const DocumentSchema = GeneratedDocument.and(
  z.object({
    id: z.string().startsWith("doc_"),
    session_id: z.string().startsWith("ses_"),
    display_name: z.string().min(1),
    file_type: z.enum(["pdf", "docx", "jpg", "png", "tiff"]),
    content_sha256: z.string().length(64),
    page_count: z.number().int().nonnegative().nullable().optional(),
    status: z.string(),
    exclude_from_drafting: z.boolean(),
    treat_as_secondary_evidence: z.boolean(),
  }),
);

export const UploadRejectionSchema = GeneratedRejection.and(
  z.object({
    display_name: z.string().min(1),
    error_code: z.string(),
    message: z.string(),
  }),
);

export const DocumentUploadBatchSchema = GeneratedBatch.and(
  z.object({
    accepted: z.array(DocumentSchema).default([]),
    rejected: z.array(UploadRejectionSchema).default([]),
  }),
);

export const ErrorEnvelopeSchema = z.object({
  error_code: z.string(),
  message: z.string(),
  details: z.record(z.string(), z.unknown()).optional(),
  session_id: z.string().nullable().optional(),
  document_id: z.string().nullable().optional(),
  request_id: z.string().nullable().optional(),
});

export type Document = z.infer<typeof DocumentSchema>;
export type UploadRejection = z.infer<typeof UploadRejectionSchema>;
export type DocumentUploadBatch = z.infer<typeof DocumentUploadBatchSchema>;
export type ErrorEnvelope = z.infer<typeof ErrorEnvelopeSchema>;
