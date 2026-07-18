/* AUTO-GENERATED — do not edit by hand. */
import { z } from "zod"

export const ErrorEnvelopeSchema = z.object({ "details": z.record(z.any()).optional(), "document_id": z.union([z.string(), z.null()]).default(null), "error_code": z.union([z.any(), z.string()]), "message": z.string(), "request_id": z.union([z.string(), z.null()]).default(null), "session_id": z.union([z.string(), z.null()]).default(null) }).strict()

