/**
 * Phase 2 page / span / token / process-event wire schemas.
 */
import { z } from "zod";
import { DocumentPageSchema as GeneratedPage } from "./generated/DocumentPage";
import { SourceSpanSchema as GeneratedSpan } from "./generated/SourceSpan";
import { SourceTokenSchema as GeneratedToken } from "./generated/SourceToken";

export const DocumentPageSchema = GeneratedPage.and(
  z.object({
    id: z.string().min(1),
    document_id: z.string().startsWith("doc_"),
    page_number: z.number().int().positive(),
    width: z.number().positive(),
    height: z.number().positive(),
    route: z.enum(["native", "ocr", "manual_review"]),
    quality_flags: z.array(z.string()),
  }),
);

export const SourceTokenSchema = GeneratedToken.and(
  z.object({
    id: z.string().startsWith("tok_"),
    document_id: z.string().startsWith("doc_"),
    page_number: z.number().int().positive(),
    text: z.string(),
    confidence: z.number().min(0).max(1),
    polygon: z.array(z.array(z.number()).min(2)).min(3),
    method: z.enum(["native", "ocr", "manual"]),
  }),
);

export const SourceSpanSchema = GeneratedSpan.and(
  z.object({
    id: z.string().startsWith("span_"),
    document_id: z.string().startsWith("doc_"),
    page_number: z.number().int().positive(),
    text: z.string(),
    token_ids: z.array(z.string()),
    polygons: z.array(z.array(z.array(z.number()).min(2)).min(3)).min(1),
    method: z.enum(["native", "ocr", "manual"]),
  }),
);

export const ProcessEventSchema = z.object({
  sequence: z.number().int().nonnegative(),
  event: z.string(),
  session_id: z.string().startsWith("ses_"),
  document_id: z.string().nullable().optional(),
  page_number: z.number().int().positive().nullable().optional(),
  status: z.string().nullable().optional(),
  message: z.string().nullable().optional(),
  progress: z.number().min(0).max(1).nullable().optional(),
  error_code: z.string().nullable().optional(),
});

export type DocumentPage = z.infer<typeof DocumentPageSchema>;
export type SourceToken = z.infer<typeof SourceTokenSchema>;
export type SourceSpan = z.infer<typeof SourceSpanSchema>;
export type ProcessEvent = z.infer<typeof ProcessEventSchema>;
